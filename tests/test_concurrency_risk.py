from hashmarks.codemap import CodeMap


def test_rmw_risk_nominates_same_owner_read_then_write(tmp_path):
    (tmp_path / "store.py").write_text(
        "def bump(store):\n current=store.get('generation')\n store.set('generation',current+1)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["store.py"])
    f = result["findings"][0]
    assert f["code"] == "python-read-modify-write-without-visible-guard"
    assert f["read_call"] == "store.get" and f["write_call"] == "store.set"
    assert result["summary"]["unguarded"] == 1


def test_rmw_risk_recognizes_visible_transaction_guard(tmp_path):
    (tmp_path / "store.py").write_text(
        "def bump(store):\n with store.transaction():\n  current=store.get('generation')\n  store.set('generation',current+1)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["store.py"])
    assert result["findings"][0]["guarded"] is True
    assert result["summary"]["unguarded"] == 0


def test_os_read_write_different_file_descriptors_are_not_one_rmw_owner(tmp_path):
    (tmp_path / "copy.py").write_text(
        "import os\ndef copy(source_fd,destination_fd):\n chunk=os.read(source_fd,4096)\n os.write(destination_fd,chunk)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["copy.py"])
    assert result["findings"] == []


def test_os_read_write_same_file_descriptor_remains_rmw_nomination(tmp_path):
    (tmp_path / "state.py").write_text(
        "import os\ndef rewrite(fd):\n chunk=os.read(fd,4096)\n os.write(fd,chunk)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["state.py"])
    finding = result["findings"][0]
    assert finding["read_call"] == "os.read"
    assert finding["write_call"] == "os.write"


def test_aliased_os_read_write_bind_file_descriptor_owner(tmp_path):
    (tmp_path / "copy.py").write_text(
        "import os as operating_system\ndef copy(source_fd,destination_fd):\n chunk=operating_system.read(source_fd,4096)\n operating_system.write(destination_fd,chunk)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["copy.py"])
    assert result["findings"] == []


def test_rmw_risk_ignores_function_local_fresh_mapping(tmp_path):
    (tmp_path / "local.py").write_text(
        "def merge(values):\n"
        " result = {}\n"
        " current = result.get('value')\n"
        " result.update(value=current)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["local.py"])
    assert result["findings"] == []


def test_rmw_risk_keeps_parameter_owned_mapping(tmp_path):
    (tmp_path / "shared.py").write_text(
        "def merge(store):\n"
        " current = store.get('value')\n"
        " store.update(value=current)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["shared.py"])
    assert len(result["findings"]) == 1
    assert result["findings"][0]["read_call"] == "store.get"
    assert result["findings"][0]["write_call"] == "store.update"


def test_rmw_risk_ignores_contextvar_owner(tmp_path):
    (tmp_path / "context_state.py").write_text(
        "from contextvars import ContextVar\n"
        "state = ContextVar('state', default=None)\n"
        "def ensure():\n"
        " current = state.get()\n"
        " if current is None:\n"
        "  state.set({})\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["context_state.py"])
    assert result["findings"] == []


def test_rmw_risk_ignores_runvar_owner(tmp_path):
    (tmp_path / "run_state.py").write_text(
        "from anyio.lowlevel import RunVar\n"
        "state = RunVar[dict]('state')\n"
        "def ensure():\n"
        " try:\n"
        "  return state.get()\n"
        " except LookupError:\n"
        "  state.set({})\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["run_state.py"])
    assert result["findings"] == []


def test_rmw_risk_does_not_suppress_reassigned_local_alias(tmp_path):
    (tmp_path / "alias.py").write_text(
        "def mutate(shared):\n"
        " local = {}\n"
        " local = shared\n"
        " current = local.get('value')\n"
        " local.update(value=current)\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        result = c.concurrency_risk_findings(["alias.py"])
    assert len(result["findings"]) == 1
