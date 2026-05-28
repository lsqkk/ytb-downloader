"""Tests for the state module."""

import json
import os

from ytb_downloader import state as st

SAMPLE_CONFIG = {
    "workers": 3,
    "proxy": "http://127.0.0.1:7890",
    "output_dir": "test_output",
    "max_duration": 600,
    "categories": [
        {"name": "cat_a", "target": 10, "queries": ["q1"]},
        {"name": "cat_b", "target": 20, "queries": ["q2"]},
        {"name": "cat_c", "target": 5, "queries": ["q3"]},
    ],
}


def test_init_state_counts():
    """State should compute correct totals."""
    state = st.init_state(SAMPLE_CONFIG)
    assert state["overall"]["total_categories"] == 3
    assert state["overall"]["total_target"] == 35  # 10 + 20 + 5
    assert state["overall"]["is_running"] is True
    assert len(state["categories"]) == 3
    assert "cat_a" in state["categories"]
    assert state["categories"]["cat_a"]["target"] == 10


def test_init_state_starts_pending():
    state = st.init_state(SAMPLE_CONFIG)
    for _name, cat in state["categories"].items():
        assert cat["status"] in ("pending", "completed")
        assert cat["downloaded"] >= 0
        assert cat["failed"] == 0


def test_set_category_state():
    state = st.init_state(SAMPLE_CONFIG)
    st.set_category_state(state, "cat_a", downloaded=5, status="running")
    assert state["categories"]["cat_a"]["downloaded"] == 5
    assert state["categories"]["cat_a"]["status"] == "running"


def test_set_current():
    state = st.init_state(SAMPLE_CONFIG)
    st.set_current(
        state,
        category="cat_a",
        video_id="abc123",
        title="Test Video",
        status="downloading",
        message="5/10",
    )
    assert state["current"]["category"] == "cat_a"
    assert state["current"]["video_id"] == "abc123"
    assert state["current"]["message"] == "5/10"


def test_add_log():
    state = st.init_state(SAMPLE_CONFIG)
    st.add_log(state, "test message")
    assert len(state["log"]) == 1
    assert state["log"][0]["message"] == "test message"


def test_add_log_truncation():
    state = st.init_state(SAMPLE_CONFIG)
    for i in range(250):
        st.add_log(state, f"msg {i}")
    assert len(state["log"]) <= 200  # should be truncated to 200


def test_overall():
    state = st.init_state(SAMPLE_CONFIG)
    st.set_overall(state, completed_categories=1)
    assert state["overall"]["completed_categories"] == 1


def test_finalize():
    state = st.init_state(SAMPLE_CONFIG)
    st.finalize(state)
    assert state["overall"]["is_running"] is False
    assert state["current"]["status"] == "completed"


def test_state_file_created():
    """init_state should write the state file."""
    state_file = "download_state.json"
    if os.path.exists(state_file):
        os.unlink(state_file)
    try:
        st.init_state(SAMPLE_CONFIG)
        assert os.path.exists(state_file)
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["overall"]["total_categories"] == 3
    finally:
        if os.path.exists(state_file):
            os.unlink(state_file)


def test_load_state():
    state_file = "download_state.json"
    if os.path.exists(state_file):
        os.unlink(state_file)
    try:
        st.init_state(SAMPLE_CONFIG)
        loaded = st.load_state()
        assert loaded is not None
        assert loaded["overall"]["total_target"] == 35
    finally:
        if os.path.exists(state_file):
            os.unlink(state_file)


def test_load_state_nonexistent():
    state_file = "download_state.json"
    if os.path.exists(state_file):
        os.unlink(state_file)
    assert st.load_state() is None


def test_state_none_handling():
    """State functions should handle None gracefully."""
    st.set_category_state(None, "test", downloaded=5)  # should not crash
    st.set_current(None, status="test")  # should not crash
    st.add_log(None, "test")  # should not crash
    st.set_overall(None, is_running=False)  # should not crash
    st.finalize(None)  # should not crash


def test_init_state_with_existing_files(tmp_path):
    """If mp4 files exist, state should count them."""
    output_dir = tmp_path / "downloads"
    cat_dir = output_dir / "cat_a"
    cat_dir.mkdir(parents=True)
    # Create some fake mp4 files
    for i in range(3):
        (cat_dir / f"000{i + 1}_abc{i}.mp4").write_text("fake")
    # Create _downloaded.json
    (cat_dir / "_downloaded.json").write_text(json.dumps({"ids": ["abc1", "abc2", "abc3"]}))

    config = {
        "workers": 3,
        "output_dir": str(output_dir),
        "categories": [
            {"name": "cat_a", "target": 10, "queries": ["q"]},
        ],
    }
    state = st.init_state(config)
    assert state["categories"]["cat_a"]["downloaded"] == 3
    assert state["categories"]["cat_a"]["status"] == "pending"  # 3 < 10
