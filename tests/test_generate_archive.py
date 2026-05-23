import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiida_mpds_monitor.generate_archive import generate_parent_archive


class DummyRetrievedFolder:
    def __init__(self, folder_path: Path):
        self._folder_path = folder_path

    def list_object_names(self):
        return [path.name for path in self._folder_path.iterdir() if path.is_file()]

    def open(self, name, mode):
        return open(self._folder_path / name, mode)


def _create_retrieved_folder(tmp_path: Path, files):
    repo_dir = tmp_path / "retrieved"
    repo_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        with (repo_dir / name).open("wb") as fh:
            fh.write(content)
    return DummyRetrievedFolder(repo_dir)


def _fake_archive_and_save(source_dir, *args, **kwargs):
    archive_path = Path(str(source_dir) + ".7z")
    archive_path.write_bytes(b"fake archive")
    return archive_path


@patch("aiida_mpds_monitor.generate_archive.archive_and_save", side_effect=_fake_archive_and_save)
@patch("aiida_mpds_monitor.generate_archive.load_node")
def test_generate_parent_archive_creates_named_root(mock_load_node, mock_archive_and_save):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir) / "tmp"
        parent_uuid = "00000000-0000-0000-0000-000000000000"
        parent_label = "NaCl_225_cF8"

        parent = MagicMock()
        parent.label = parent_label
        parent.called = []
        mock_load_node.return_value = parent

        # Child workchain with two grandchildren.
        grandchild_opt = MagicMock()
        grandchild_opt.label = "OPTIMISE"
        grandchild_opt.pk = 1
        grandchild_opt.outputs.retrieved = _create_retrieved_folder(Path(tmp_dir) / "opt_repo", {"OUTPUT": b"opt"})

        grandchild_phon = MagicMock()
        grandchild_phon.label = "PHON"
        grandchild_phon.pk = 2
        grandchild_phon.outputs.retrieved = _create_retrieved_folder(Path(tmp_dir) / "phon_repo", {"OUTPUT": b"phon"})

        child = MagicMock()
        child.called = [grandchild_opt, grandchild_phon]

        archive_path = generate_parent_archive(
            parent_uuid, base_nodes=[child], tmp_root=tmp_root
        )

        assert archive_path is not None
        assert archive_path.name == "NaCl_225_cF8.7z"
        assert archive_path.exists()
        assert archive_path.read_bytes() == b"fake archive"

        expected_archive_root = tmp_root / parent_uuid / parent_label
        mock_archive_and_save.assert_called_once_with(expected_archive_root, aiida=True, skip_errors=True)
        assert not (tmp_root / parent_uuid).exists()
