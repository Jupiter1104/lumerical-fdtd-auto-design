import asyncio


def test_all_expected_mcp_tools_register():
    from src import server

    server.register_all_tools()
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}

    assert {
        "fdtd_health",
        "fdtd_session_start",
        "fdtd_session_pause",
        "fdtd_session_close",
        "fdtd_save",
        "fdtd_load",
        "fdtd_add_fdtd_region",
        "fdtd_add_rect",
        "fdtd_add_circle",
        "fdtd_job_plan",
        "fdtd_job_start",
        "fdtd_job_status",
        "fdtd_job_tasks",
        "fdtd_job_resume",
        "fdtd_metasurface_sweep_plan",
        "fdtd_metasurface_sweep_start",
        "fdtd_sweep_config_get",
        "fdtd_sweep_config_set",
        "fdtd_sweep_run",
        "fdtd_sweep_status",
        "fdtd_sweep_monitor",
        "fdtd_results_list",
        "fdtd_results_download",
        "fdtd_export_gds",
        "fdtd_export_data",
        "fdtd_device_template",
        "fdtd_list_devices",
        "fdtd_troubleshoot",
        "fdtd_best_practices",
    } == registered
