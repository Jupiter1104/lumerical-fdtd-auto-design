# FDTD Simulation Workflow Guide

Status note: the standard workflow below describes the target production
workflow. The current MCP surface registers session, model, geometry, sweep,
results, export, and knowledge tools. Job/task, approval, resume, and quality
report endpoints are still planned work and must not be assumed available.

## Standard Workflow

```
1. Compile Requirement
   natural language -> SimulationPlan
          │
          ▼
2. Plan
   validate schema / paths / units
   expand tasks and report cost
          │
          ▼
3. Optional Mock
   verify RPC / job state / postprocess
   never treat mock output as physics
          │
          ▼
4. Approve Real Run
   report model, job ID, task count,
   GUI mode, resources, overwrite risk
          │
          ▼
5. Start Session
   fdtd_session_start()
          │
          ▼
6. Set Up Simulation Region
   fdtd_add_fdtd_region(dimension="3D", x_span=8e-6, ...)
          │
          ▼
7. Build Geometry (layer by layer)
   fdtd_add_rect(name="substrate", material="SiO2", ...)
   fdtd_add_rect(name="waveguide", material="Si", ...)
          │
          ▼
8. Add Source
   fdtd_eval("addmode(); ...")
          │
          ▼
9. Add Monitors
   fdtd_eval("addpower(); ...")
          │
          ▼
10. Save & Start Asynchronous Job
    fdtd_save("<job>/models/project.fsp")
    submit -> job_id/task_id
          │
          ▼
11. Poll Compact Status
    state / completed / failed / missing / short log tail
          │
          ▼
12. Verify Results
   fdtd_get_result("monitor", "T")
   fdtd_physical_check("monitor", "transmission")
          │
          ▼
13. Quality Gate
    summary.json + quality_report.json
    pass / warning / fail
          │
          ▼
14. Suggest Next Run
    produce a new plan; do not automatically expand real work
          │
          ▼
15. Export & Stop
   fdtd_export_gds("layout.gds")
   fdtd_save("project_final.fsp")
   fdtd_session_close()
```

Operational rules:

- A solver-completed state is not a physical-quality conclusion.
- Jobs expected to exceed 30 seconds must return an ID and run asynchronously.
- Resume only compatible tasks with unchanged physical settings.
- Default collection is evidence-first; download per-task `.fsp` files only for debugging.

## SOI Waveguide Simulation

For a standard 220nm SOI platform at 1550nm:

1. Substrate: SiO2, 2um thick
2. Core: Si, 220nm thick, 450-500nm wide (TE single-mode)
3. Cladding: SiO2 (optional, can use air)
4. Source: TE mode source, 1500-1600nm
5. Monitor: Z-normal frequency-domain power monitor at output

Key checks:
- Effective index around 2.4-2.8 for TE0 at 450nm width
- Single-mode condition: width < ~550nm
- PML distance from structures: > lambda/2 (~800nm)

## MMI 1x2 Design Workflow

1. Input waveguide: 450nm wide, straight
2. Input taper: linear, 450nm → taper_width, length > 5um
3. MMI region: width > 2*wg_width, length from self-image formula
4. Output tapers: mirror of input tapers
5. Output waveguides: 450nm wide, separated by > 2um

Optimization parameters (in order):
1. MMI length — primary determinant of splitting ratio
2. MMI width — secondary, affects excess loss
3. Taper width — finer adjustment
4. Taper length — once others are fixed

## Parameter Sweep Pattern

```
fdtd_sweep("wg_width", [400e-9, 450e-9, 500e-9, 550e-9], "monitor", "T")
```

This sets the parameter, re-runs, and collects T for each value.
Use to find single-mode cutoff, optimize coupling, etc.
