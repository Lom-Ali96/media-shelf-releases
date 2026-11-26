import concurrent.futures as cf

from poeci.storage import db


def test_connection_survives_many_threads(tmp_path):
    # Regression: one shared sqlite3 connection used by several server threads
    # raised "bad parameter or other API misuse" (stress test, 2026-11-26).
    conn = db.connect(tmp_path / "t.sqlite3")

    def work(i):
        db.set_setting(conn, f"k{i}", str(i))
        return db.get_setting(conn, f"k{i}")

    with cf.ThreadPoolExecutor(16) as ex:
        assert list(ex.map(work, range(400))) == [str(i) for i in range(400)]
    assert len(conn.execute("SELECT * FROM settings").fetchall()) == 400
