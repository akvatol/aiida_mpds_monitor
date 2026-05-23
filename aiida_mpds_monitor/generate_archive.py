import json
import shutil
from pathlib import Path
from typing import Optional, List

from aiida import load_profile as load_aiida_profile
from aiida.orm import load_node, WorkChainNode

import re

load_aiida_profile()

from dft_organizer.core import archive_and_save

LABEL_DICT = {
    "Elastic constants":"ELASTIC",
    "Phonon frequencies":"PHONON",
    "Geometry optimization":"STRUCT",
    "":"TRANSPORT",
    "":"ELECTRON",
}

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


def _safe_dir_name(name: str) -> str:
    """Create a filesystem-safe directory name from a node label."""
    return str(name).strip().replace("/", "_")


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

    repo_folder = getattr(calc.outputs, "retrieved", None)
    if repo_folder is None:
        print(f"No retrieved folder for calculation {uuid}")
        return None

    if tmp_root is None:
        tmp_root = Path.cwd() / "aiida_archives_tmp"
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
            with repo_folder.open(name, "rb") as src, (calc_dir / name).open("wb") as dst:
                shutil.copyfileobj(src, dst)
    except Exception as e:
        print(f"Error copying files for {uuid}: {e}")
        return None

    # Write INPUT.json if parameters are present
    try:
        params = None
        if hasattr(calc.inputs, "parameters"):
            try:
                params = calc.inputs.parameters.get_dict()
            except Exception:
                params = None

        if params:
            with (calc_dir / "INPUT.json").open("w") as f:
                json.dump(params, f, indent=2, default=str)
    except Exception:
        pass

    # Ensure OUTPUT or scheduler stderr is present in the archive
    try:
        names = repo_folder.list_object_names()
        if "OUTPUT" in names:
            with repo_folder.open("OUTPUT", "rb") as src, (calc_dir / "OUTPUT").open("wb") as dst:
                shutil.copyfileobj(src, dst)
        elif "_scheduler-stderr.txt" in names:
            with (
                repo_folder.open("_scheduler-stderr.txt", "rb") as src,
                (calc_dir / "_scheduler-stderr.txt").open("wb") as dst,
            ):
                shutil.copyfileobj(src, dst)
    except Exception:
        pass

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


def generate_parent_archive(
    parent_uuid: str,
    base_nodes: Optional[List[WorkChainNode]] = None,
    archive_path: Optional[Path] = None,
    tmp_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Generate a 7z archive for the parent WorkChain with subdirectories for each
    grandchild calculation.

    Uses a temporary directory under ``tmp_root/{parent_uuid}`` and removes it
    after compression.
    """
    try:
        parent = load_node(parent_uuid)
    except Exception as e:
        print(f"Failed to load parent node {parent_uuid}: {e}")
        return None

    if base_nodes is None:
        base_nodes = list(parent.called) if hasattr(parent, "called") else []

    if not base_nodes:
        print(f"No child nodes found for parent {parent_uuid}")
        return None

    if tmp_root is None:
        tmp_root = Path.cwd() / "aiida_archives_tmp"
    tmp_root = Path(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)

    parent_tmp = tmp_root / parent_uuid
    parent_label = getattr(parent, "label", None) or parent_uuid
    parent_dir_name = _safe_dir_name(parent_label)
    archive_root = parent_tmp / parent_dir_name

    # Remove any existing temp dir for this parent, then create fresh
    if parent_tmp.exists():
        shutil.rmtree(parent_tmp)
    archive_root.mkdir(parents=True, exist_ok=True)

    try:
        # Process each child workchain and collect data from its grandchildren
        for child_node in base_nodes:
            if not isinstance(child_node, WorkChainNode):
                continue

            grandchildren = child_node.called if hasattr(child_node, "called") else []
            for grandchild in grandchildren:
                label = getattr(grandchild, "label", None)
                if not label or not str(label).strip():
                    continue

                label_ = str(label).strip()
                label_ = label_.replace("/", "_")
                if res := re.search(r"\s(\w+\s\w+)\s(?=\[\d\])", label_):
                    label_ = res.group(1)
                    label_str = LABEL_DICT.get(label_, label_)
                grandchild_dir = archive_root / label_str
                grandchild_dir.mkdir(parents=True, exist_ok=True)


                try:
                    repo_folder = getattr(grandchild.outputs, "retrieved", None)
                    if repo_folder is not None:
                        names = repo_folder.list_object_names()
                        for name in names:
                            try:
                                with repo_folder.open(name, "rb") as src, (grandchild_dir / name).open("wb") as dst:
                                    shutil.copyfileobj(src, dst)
                            except Exception as e:
                                print(
                                    f"Warning: Could not copy {name} from {label_} "
                                    f"{grandchild.pk}: {e}"
                                )
                except Exception as e:
                    print(
                        f"Warning: Could not access retrieved folder for {label_} "
                        f"{grandchild.pk}: {e}"
                    )

                try:
                    params = None
                    if hasattr(grandchild.inputs, "parameters"):
                        try:
                            params = grandchild.inputs.parameters.get_dict()
                        except Exception:
                            params = None

                    if params:
                        with (grandchild_dir / "INPUT.json").open("w") as f:
                            json.dump(params, f, indent=2, default=str)
                except Exception as e:
                    print(
                        f"Warning: Could not save INPUT.json for {label_} "
                        f"{grandchild.pk}: {e}"
                    )

                try:
                    repo_folder = getattr(grandchild.outputs, "retrieved", None)
                    if repo_folder is not None:
                        names = repo_folder.list_object_names()
                        if "OUTPUT" in names:
                            with repo_folder.open("OUTPUT", "rb") as src, (grandchild_dir / "OUTPUT").open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                        elif "_scheduler-stderr.txt" in names:
                            with (
                                repo_folder.open("_scheduler-stderr.txt", "rb") as src,
                                (grandchild_dir / "_scheduler-stderr.txt").open("wb") as dst,
                            ):
                                shutil.copyfileobj(src, dst)
                except Exception:
                    pass

        if archive_path is None:
            archive_path = tmp_root.parent / f"{parent_dir_name}.7z"
        archive_path = Path(archive_path)

        # archive_and_save creates {archive_root}.7z next to archive_root
        _ = archive_and_save(archive_root, aiida=True, skip_errors=True)

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


if __name__ == "__main__":
    generate_parent_archive("64af6cab-5380-4f66-a37f-e8179455a5f9")
