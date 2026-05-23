import json
import re
import shutil
from pathlib import Path
from typing import Optional, List, Tuple

from aiida import load_profile as load_aiida_profile
from aiida.orm import load_node, WorkChainNode

load_aiida_profile()

from dft_organizer.core import archive_and_save


# ---------------------------------------------------------------------------
#  Normalizers / sanitizers
# ---------------------------------------------------------------------------

_SANITIZE_RE = re.compile(r'[^A-Za-z0-9_]')


def _normalize_label(raw_label: str) -> Tuple[str, str]:
    """Split a grandchild label into (structure_name, task_name).

    Examples
    --------
    'Ba2LaPaO6/225: Geometry optimization [1]' ->
    ('Ba2LaPaO6_225', 'OPTIMISE')

    'C/227/cF8: Phonon frequencies [1]' ->
    ('C_227_cF8', 'PHON')
    """
    raw_label = raw_label.strip()

    # Remove trailing retry annotations: " [1]", " [2] - restart", etc.
    clean = re.sub(r'\s*\[\d+\](\s+-\s+restart)?$', '', raw_label)

    #  e.g. 'C/227/cF8: Geometry optimization'
    if ':' in clean:
        structure_part, task_part = clean.rsplit(':', 1)
    else:
        # Parent-only label, e.g. 'C/227/cF8'
        structure_part, task_part = clean, ''

    structure_name = _SANITIZE_RE.sub('_', structure_part.strip())
    task_name = _task_from_string(task_part.strip())

    return structure_name, task_name


def _task_from_string(task_str: str) -> str:
    """Map common task descriptions to a short uppercase token."""
    task_lower = task_str.lower()
    if any(word in task_lower for word in ['optimise', 'optimize', 'optimization']):
        return 'OPTIMISE'
    if any(word in task_lower for word in ['phonon', 'frequency', 'frequencies']):
        return 'PHON'
    if any(word in task_lower for word in ['elastic', 'elast']):
        return 'ELAST'
    if any(word in task_lower for word in ['band', 'bands']):
        return 'BAND'
    if any(word in task_lower for word in ['dos', 'density', 'state']):
        return 'DOS'
    if task_str:
        return _SANITIZE_RE.sub('_', task_str).upper()
    return 'UNKNOWN'


def _sanitize_for_filename(s: str) -> str:
    """Replace unsafe characters with underscores."""
    return _SANITIZE_RE.sub('_', s.strip())


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _finalize_archive(source_dir: Path, dest_path: Path) -> Optional[Path]:
    """Confirm that archive_and_save created the expected archive and move it if needed.

    archive_and_save always writes ``{resolved_source_dir}.7z`` next to the source
    directory. If *dest_path* differs from that location, the file is moved.
    Returns the path to the final archive, or ``None`` if nothing was created.
    """
    resolved = Path(source_dir).resolve()
    expected = resolved.parent / f"{resolved.name}.7z"
    if not expected.exists():
        return None

    dest = Path(dest_path)
    if dest.resolve() != expected:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(expected), str(dest))

    return dest


def _copy_retrieved_files(grandchild, dest_dir: Path) -> None:
    """Copy retrieved files from *grandchild* into *dest_dir*."""
    repo_folder = getattr(grandchild.outputs, 'retrieved', None)
    if repo_folder is None:
        return

    try:
        names = repo_folder.list_object_names()
        for name in names:
            try:
                with repo_folder.open(name, 'rb') as src, (dest_dir / name).open('wb') as dst:
                    shutil.copyfileobj(src, dst)
            except Exception as e:
                print(f"Warning: Could not copy {name} {grandchild.pk}: {e}")
    except Exception as e:
        print(f"Warning: Could not access retrieved folder {grandchild.pk}: {e}")


def _write_input_json(grandchild, dest_dir: Path) -> None:
    """Write an ``INPUT.json`` into *dest_dir* if the grandchild has parameters."""
    try:
        params = None
        if hasattr(grandchild.inputs, 'parameters'):
            try:
                params = grandchild.inputs.parameters.get_dict()
            except Exception:
                params = None

        if params:
            with (dest_dir / 'INPUT.json').open('w') as f:
                json.dump(params, f, indent=2, default=str)
    except Exception as e:
        print(f"Warning: Could not save INPUT.json {grandchild.pk}: {e}")


def _copy_output_or_stderr(grandchild, dest_dir: Path) -> None:
    """Ensure OUTPUT or scheduler stderr ends up in *dest_dir*."""
    repo_folder = getattr(grandchild.outputs, 'retrieved', None)
    if repo_folder is None:
        return

    try:
        names = repo_folder.list_object_names()
        if 'OUTPUT' in names:
            with repo_folder.open('OUTPUT', 'rb') as src, (dest_dir / 'OUTPUT').open('wb') as dst:
                shutil.copyfileobj(src, dst)
        elif '_scheduler-stderr.txt' in names:
            with (
                repo_folder.open('_scheduler-stderr.txt', 'rb') as src,
                (dest_dir / '_scheduler-stderr.txt').open('wb') as dst,
            ):
                shutil.copyfileobj(src, dst)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  Single-node archive (legacy / convenience)
# ---------------------------------------------------------------------------

def generate_archive(
    uuid: str,
    archive_path: Optional[Path] = None,
    tmp_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Generate a 7z archive for the AiiDA calculation with given UUID.

    Creates a temporary folder with the calculation's retrieved files and
    an ``INPUT.json`` (if parameters exist), then compresses it using
    :func:`dft_organizer.core.archive_and_save`.
    """
    try:
        calc = load_node(uuid)
    except Exception as e:
        print(f"Failed to load node {uuid}: {e}")
        return None

    repo_folder = getattr(calc.outputs, 'retrieved', None)
    if repo_folder is None:
        print(f"No retrieved folder for calculation {uuid}")
        return None

    if tmp_root is None:
        tmp_root = Path.cwd() / 'aiida_archives_tmp'
    tmp_root = Path(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)

    calc_dir = tmp_root / uuid
    if calc_dir.exists():
        shutil.rmtree(calc_dir)
    calc_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files from retrieved folder
    try:
        names = repo_folder.list_object_names()
        for name in names:
            with repo_folder.open(name, 'rb') as src, (calc_dir / name).open('wb') as dst:
                shutil.copyfileobj(src, dst)
    except Exception as e:
        print(f"Error copying files for {uuid}: {e}")
        return None

    # Write INPUT.json if parameters are present
    _write_input_json(calc, calc_dir)

    # Ensure OUTPUT or scheduler stderr is present in the archive
    _copy_output_or_stderr(calc, calc_dir)

    if archive_path is None:
        archive_path = tmp_root.parent / f"{uuid}.7z"
    archive_path = Path(archive_path)

    # archive_and_save creates {calc_dir}.7z next to calc_dir
    _ = archive_and_save(calc_dir, make_report=False)

    result = _finalize_archive(calc_dir, archive_path)
    if result:
        print(f"Archive created: {result}")
    else:
        print(f"Failed to create archive for {uuid}")
    return result


# ---------------------------------------------------------------------------
#  Parent-node archive (structured:  structure_name/PHON, OPTIMISE ... )
# ---------------------------------------------------------------------------

def generate_parent_archive(
    parent_uuid: str,
    base_nodes: Optional[List[WorkChainNode]] = None,
    archive_path: Optional[Path] = None,
    tmp_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Generate a 7z archive for the parent WorkChain.

    Inside the archive the layout is::

        <structure_name>/
            OPTIMISE/
            PHON/
            ELAST/
            ...

    * ``structure_name`` is derived from the parent label (e.g.
      ``'C/227/cF8'`` -> ``'C_227_cF8'``).
    * Task sub-folders are grouped by grandchild task type (e.g. *Geometry
      optimization* -> ``OPTIMISE``).
    """
    try:
        parent = load_node(parent_uuid)
    except Exception as e:
        print(f"Failed to load parent node {parent_uuid}: {e}")
        return None

    if base_nodes is None:
        base_nodes = list(parent.called) if hasattr(parent, 'called') else []

    if not base_nodes:
        print(f"No child nodes found for parent {parent_uuid}")
        return None

    # -- Archive name from parent label --------------------------------------
    parent_label = getattr(parent, 'label', '') or ''
    structure_name = _SANITIZE_RE.sub('_', parent_label.strip())
    if not structure_name:
        structure_name = parent_uuid

    # -- Temp layout ---------------------------------------------------------
    if tmp_root is None:
        tmp_root = Path.cwd() / 'aiida_archives_tmp'
    tmp_root = Path(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)

    parent_tmp = tmp_root / parent_uuid
    archive_root = parent_tmp / structure_name

    if parent_tmp.exists():
        shutil.rmtree(parent_tmp)
    archive_root.mkdir(parents=True, exist_ok=True)

    try:
        # -- Group grandchildren by task -------------------------------------
        for child_node in base_nodes:
            if not isinstance(child_node, WorkChainNode):
                continue

            grandchildren = child_node.called if hasattr(child_node, 'called') else []
            for grandchild in grandchildren:
                label = getattr(grandchild, 'label', None)
                if not label or not str(label).strip():
                    continue

                label_str = str(label).strip()
                _struct, task_name = _normalize_label(label_str)

                # Build the sub-directory:  structure_name/TASK/
                task_dir = archive_root / task_name
                task_dir.mkdir(parents=True, exist_ok=True)

                # Each grandchild gets its own folder inside the task folder
                # named after the raw label (sanitised) so multiple retries
                # of the same task do not clobber one another.
                gc_dir_name = _sanitize_for_filename(label_str)
                gc_dir = task_dir / gc_dir_name
                gc_dir.mkdir(parents=True, exist_ok=True)

                _copy_retrieved_files(grandchild, gc_dir)
                _write_input_json(grandchild, gc_dir)
                _copy_output_or_stderr(grandchild, gc_dir)

        # -- Compress ---------------------------------------------------------
        if archive_path is None:
            archive_path = tmp_root.parent / f"{structure_name}.7z"
        archive_path = Path(archive_path)

        _ = archive_and_save(archive_root, make_report=False)

        result = _finalize_archive(archive_root, archive_path)
        if result:
            print(f"Parent archive created: {result}")
        else:
            print("Failed to create parent archive")
        return result

    finally:
        # Always attempt to remove the temporary directory
        try:
            if parent_tmp.exists():
                shutil.rmtree(parent_tmp)
        except Exception as e:
            print(f"Warning: Failed to clean up temp dir {parent_tmp}: {e}")


if __name__ == '__main__':
    generate_parent_archive("64af6cab-5380-4f66-a37f-e8179455a5f9")
