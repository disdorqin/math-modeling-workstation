from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.source_collector import SourceCollector


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass


def test_url_collection_preserves_snapshot_and_metadata(tmp_path: Path) -> None:
    served = tmp_path / "served"
    served.mkdir()
    (served / "data.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    handler = lambda *args, **kwargs: QuietHandler(*args, directory=str(served), **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cases = CaseManager(tmp_path / "output")
        case = cases.create_case("SM", "Source")
        artifacts = ArtifactRegistry(cases)
        record = SourceCollector(cases, artifacts).collect_url(
            case["case_id"], f"http://127.0.0.1:{server.server_port}/data.csv"
        )
        artifact = artifacts.get(case["case_id"], record["artifact_id"])
        assert artifact["sha256"] == record["sha256"]
        assert (cases.case_root(case["case_id"]) / artifact["path"]).read_text(encoding="utf-8") == "x,y\n1,2\n"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

