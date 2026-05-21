import json
import shutil
from pathlib import Path
from typing import Optional, List

from aiida import load_profile as load_aiida_profile
from aiida.orm import load_node, WorkChainNode

load_aiida_profile()

from dft_organizer.core import compress_with_7z


def generate_archive(uuid: str, archive_path: Optional[Path] = None, tmp_root: Optional[Path] = None) -> Optional[Path]:
    """
    Generate a 7z archive for the AiiDA calculation with given UUID.

    Creates a temporary folder with the calculation's retrieved files and
    an `INPUT.json` (if parameters exist), then compresses it using
    `compress_with_7z` and returns the created archive Path or `None` on error.
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

    # copy all files from retrieved folder
    try:
        names = repo_folder.list_object_names()
        for name in names:
            with repo_folder.open(name, "rb") as src, (calc_dir / name).open("wb") as dst:
                shutil.copyfileobj(src, dst)
    except Exception as e:
        print(f"Error copying files for {uuid}: {e}")
        return None

    # write INPUT.json if parameters are present
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

    # ensure OUTPUT or scheduler stderr is present in the archive
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

    ok = compress_with_7z(calc_dir, archive_path)
    if ok:
        print(f"Archive created: {archive_path}")
        return archive_path
    else:
        print("Failed to create archive")
        return None

def generate_parent_archive(
    parent_uuid: str,
    base_nodes: Optional[List[WorkChainNode]] = None,
    archive_path: Optional[Path] = None,
    tmp_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Generate a 7z archive for the parent WorkChain with subdirectories for each grandchild calculation.

    Creates a temporary folder with structure:
    externalArchive/
      <GRANDCHILD_LABEL_1>/  (e.g., ELASTIC)
        [grandchild_1 retrieved files + INPUT.json]
      <GRANDCHILD_LABEL_2>/  (e.g., STRUCT)
        [grandchild_2 retrieved files + INPUT.json]
      ...

    Then compresses it using `compress_with_7z` and returns the created archive Path or `None` on error.

    Args:
        parent_uuid: UUID of the parent WorkChain
        base_nodes: List of child WorkChainNode objects to include in archive.
                   If None, will fetch from parent_uuid.called
        archive_path: Path where to save the archive. Defaults to tmp_root.parent / f"{parent_uuid}_external.7z"
        tmp_root: Root directory for temporary files. Defaults to current working dir / "aiida_archives_tmp"

    Returns:
        Path to the created archive or None on error
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

    # Create externalArchive root directory
    archive_root = tmp_root / parent_uuid / "externalArchive"
    if archive_root.exists():
        shutil.rmtree(archive_root.parent)
    archive_root.mkdir(parents=True, exist_ok=True)

    # Process each child workchain and collect data from its grandchildren
    for child_node in base_nodes:
        if not isinstance(child_node, WorkChainNode):
            continue

        # Get grandchildren (called nodes) from this child
        grandchildren = child_node.called if hasattr(child_node, "called") else []
        
        for grandchild in grandchildren:
            # Use label as subdirectory name (e.g., "ELASTIC", "STRUCT")
            label = getattr(grandchild, "label", None)
            if not label or not str(label).strip():
                continue
            
            label_str = str(label).strip().replace("/", "_")
            grandchild_dir = archive_root / label_str
            grandchild_dir.mkdir(parents=True, exist_ok=True)

            # Copy retrieved files from grandchild node
            try:
                repo_folder = getattr(grandchild.outputs, "retrieved", None)
                if repo_folder is not None:
                    names = repo_folder.list_object_names()
                    for name in names:
                        try:
                            with repo_folder.open(name, "rb") as src, (grandchild_dir / name).open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                        except Exception as e:
                            print(f"Warning: Could not copy {name} from {label_str} {grandchild.pk}: {e}")
            except Exception as e:
                print(f"Warning: Could not access retrieved folder for {label_str} {grandchild.pk}: {e}")

            # Write INPUT.json if parameters are present
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
                print(f"Warning: Could not save INPUT.json for {label_str} {grandchild.pk}: {e}")

            # Ensure OUTPUT or scheduler stderr is present
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
        archive_path = tmp_root.parent / f"{parent_uuid}_external.7z"
    archive_path = Path(archive_path)

    ok = compress_with_7z(archive_root.parent, archive_path)
    if ok:
        print(f"Parent archive created: {archive_path}")
        return archive_path
    else:
        print("Failed to create parent archive")
        return None


if __name__ == "__main__":
    generate_parent_archive("64af6cab-5380-4f66-a37f-e8179455a5f9")