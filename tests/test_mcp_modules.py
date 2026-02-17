"""Tests for MCP module filtering.

Tests that the module-based tag filtering correctly limits which tools are exposed.
"""

import pytest


class TestModuleConfig:
    """Tests for module configuration."""

    def test_default_modules_is_core_only(self):
        """Default config has only core module enabled."""
        from sage.config import SageConfig

        config = SageConfig()
        assert config.modules == ("core",)

    def test_modules_can_be_tuple_or_list(self):
        """Modules can be specified as tuple or list."""
        from sage.config import SageConfig

        # Tuple
        config1 = SageConfig(modules=("core", "knowledge"))
        assert config1.modules == ("core", "knowledge")

        # List should be converted when loading from YAML
        # (handled by load() method)

    def test_modules_config_load_converts_list_to_tuple(self, tmp_path):
        """Loading config converts YAML list to tuple."""
        from sage.config import SageConfig

        # Create a tuning.yaml with list syntax
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        (sage_dir / "tuning.yaml").write_text("modules:\n  - core\n  - knowledge\n")

        config = SageConfig.load(sage_dir)
        assert config.modules == ("core", "knowledge")
        assert isinstance(config.modules, tuple)


class TestToolTagging:
    """Tests for tool tags."""

    def test_all_tools_have_tags(self):
        """All MCP tools should have exactly one module tag."""
        from sage.mcp_server import mcp

        # Get all registered tools
        tools = list(mcp._tool_manager._tools.values())

        valid_modules = {"core", "knowledge", "code", "extras"}
        untagged = []
        invalid_tags = []

        for tool in tools:
            tags = tool.tags or set()
            module_tags = tags & valid_modules

            if not module_tags:
                untagged.append(tool.name)
            elif len(module_tags) > 1:
                invalid_tags.append((tool.name, module_tags))

        assert not untagged, f"Tools without module tags: {untagged}"
        assert not invalid_tags, f"Tools with multiple module tags: {invalid_tags}"

    def test_tool_count_by_module(self):
        """Verify tool counts per module."""
        from sage.mcp_server import mcp

        # Count tools by module
        module_counts = {"core": 0, "knowledge": 0, "code": 0, "extras": 0}

        tools = list(mcp._tool_manager._tools.values())
        for tool in tools:
            tags = tool.tags or set()
            for module in module_counts:
                if module in tags:
                    module_counts[module] += 1

        # Expected distribution (based on CLAUDE.md)
        assert module_counts["core"] == 8, f"Expected 8 core tools, got {module_counts['core']}"
        assert module_counts["knowledge"] == 11, f"Expected 11 knowledge tools, got {module_counts['knowledge']}"
        assert module_counts["code"] == 8, f"Expected 8 code tools, got {module_counts['code']}"
        assert module_counts["extras"] == 6, f"Expected 6 extras tools, got {module_counts['extras']}"

        # Total should be 33
        total = sum(module_counts.values())
        assert total == 33, f"Expected 33 total tools, got {total}"


class TestModuleFiltering:
    """Tests for module filtering via MCP protocol."""

    @pytest.fixture
    def get_filtered_tools(self):
        """Helper to get filtered tools at MCP protocol level."""
        import asyncio

        async def _get(mcp):
            return await mcp._list_tools_middleware()

        def sync_get(mcp):
            return asyncio.run(_get(mcp))

        return sync_get

    def test_core_only_exposes_8_tools(self, get_filtered_tools):
        """With modules=['core'], only 8 tools are exposed."""
        from fastmcp import FastMCP
        from sage.mcp_server import mcp, _enabled_modules

        # Verify our default config
        assert _enabled_modules == {"core"}

        tools = get_filtered_tools(mcp)
        assert len(tools) == 8

        tool_names = {t.name for t in tools}
        expected = {
            "version",
            "health",
            "continuity_status",
            "save_checkpoint",
            "list_checkpoints",
            "load_checkpoint",
            "search_checkpoints",
            "autosave_check",
        }
        assert tool_names == expected

    def test_filtered_tools_have_core_tag(self, get_filtered_tools):
        """All filtered tools have the 'core' tag."""
        from sage.mcp_server import mcp

        tools = get_filtered_tools(mcp)
        for tool in tools:
            assert "core" in tool.tags, f"Tool {tool.name} should have 'core' tag"


class TestModuleCategories:
    """Tests for tool module categorization."""

    def test_core_tools(self):
        """Core tools are essential checkpoint/session tools."""
        from sage.mcp_server import mcp

        core_tools = [
            t for t in mcp._tool_manager._tools.values() if "core" in (t.tags or set())
        ]

        core_names = {t.name for t in core_tools}
        expected = {
            "version",
            "health",
            "continuity_status",
            "save_checkpoint",
            "list_checkpoints",
            "load_checkpoint",
            "search_checkpoints",
            "autosave_check",
        }
        assert core_names == expected

    def test_knowledge_tools(self):
        """Knowledge tools handle knowledge base operations."""
        from sage.mcp_server import mcp

        knowledge_tools = [
            t for t in mcp._tool_manager._tools.values() if "knowledge" in (t.tags or set())
        ]

        knowledge_names = {t.name for t in knowledge_tools}
        expected = {
            "save_knowledge",
            "recall_knowledge",
            "list_knowledge",
            "remove_knowledge",
            "update_knowledge",
            "link_knowledge",
            "deprecate_knowledge",
            "archive_knowledge",
            "list_todos",
            "mark_todo_done",
            "get_pending_todos",
        }
        assert knowledge_names == expected

    def test_code_tools(self):
        """Code tools handle code indexing/search."""
        from sage.mcp_server import mcp

        code_tools = [
            t for t in mcp._tool_manager._tools.values() if "code" in (t.tags or set())
        ]

        code_names = {t.name for t in code_tools}
        expected = {
            "index_code",
            "search_code",
            "grep_symbol",
            "analyze_function",
            "mark_core",
            "list_core",
            "unmark_core",
            "code_context",
        }
        assert code_names == expected

    def test_extras_tools(self):
        """Extras tools handle config/debugging."""
        from sage.mcp_server import mcp

        extras_tools = [
            t for t in mcp._tool_manager._tools.values() if "extras" in (t.tags or set())
        ]

        extras_names = {t.name for t in extras_tools}
        expected = {
            "get_config",
            "set_config",
            "reload_config",
            "debug_query",
            "record_failure",
            "list_failures",
        }
        assert extras_names == expected
