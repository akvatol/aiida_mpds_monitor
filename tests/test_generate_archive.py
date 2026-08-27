import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aiida_mpds_monitor.generate_archive import generate_parent_archive


class DummyRetrievedFolder:
    def __init__(self, folder_path: Path):
        self._folder_path = folder_path

    def list_object_names(self):
        return [path.name for path in self._folder_path.iterdir() if path.is_file()]

    def open(self, name, mode):
        return open(self._folder_path / name, mode)


class DummyProcessNode:
    def __init__(
        self,
        *,
        uuid,
        label="",
        pk=None,
        called=None,
        retrieved=None,
        is_finished_ok=True,
    ):
        self.uuid = uuid
        self.label = label
        self.pk = pk
        self.called = list(called or [])
        self.is_finished_ok = is_finished_ok
        self.outputs = SimpleNamespace(retrieved=retrieved)
        self.inputs = SimpleNamespace()
        self.process_label = type(self).__name__
        self.process_state = SimpleNamespace(value="finished")
        self.exit_status = 0 if is_finished_ok else 1


class DummyCalcJobNode(DummyProcessNode):
    pass


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

        parent = DummyProcessNode(uuid=parent_uuid, label=parent_label)
        mock_load_node.return_value = parent

        # Child workchain with two grandchildren.
        grandchild_opt = DummyCalcJobNode(
            uuid="opt-uuid",
            label="OPTIMISE",
            pk=1,
            retrieved=_create_retrieved_folder(
                Path(tmp_dir) / "opt_repo", {"OUTPUT": b"opt"}
            ),
        )
        grandchild_phon = DummyCalcJobNode(
            uuid="phon-uuid",
            label="PHON",
            pk=2,
            retrieved=_create_retrieved_folder(
                Path(tmp_dir) / "phon_repo", {"OUTPUT": b"phon"}
            ),
        )
        child = DummyProcessNode(
            uuid="child-uuid", called=[grandchild_opt, grandchild_phon]
        )

        with patch(
            "aiida_mpds_monitor.generate_archive.CalcJobNode", DummyCalcJobNode
        ):
            archive_path = generate_parent_archive(
                parent_uuid, base_nodes=[child], tmp_root=tmp_root
            )

        assert archive_path is not None
        assert archive_path.name == "NaCl_225_cF8.7z"
        assert archive_path.exists()
        assert archive_path.read_bytes() == b"fake archive"

        expected_archive_root = tmp_root / parent_uuid / parent_label
        mock_archive_and_save.assert_called_once_with(
            expected_archive_root, aiida=True, skip_errors=True
        )
        assert not (tmp_root / parent_uuid).exists()
