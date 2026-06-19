# Metasurface template

This directory stores the local metasurface baseline model used by the native
`metasurface-sweep` job runner.

## Required file

```text
templates/metasurface/base_model.fsp
```

The `.fsp` model is intentionally ignored by Git because it is a large binary
artifact. Install it on Windows from a known-good local template:

```cmd
scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"
```

The installer copies the file to `templates\metasurface\base_model.fsp` and
prints its SHA-256 fingerprint. Each real sweep also records the template path,
size, modification time, and SHA-256 in the job `manifest.json`.

## Required FDTD contents

The template must contain:

- `FDTD`
- `::model`
- `::model::s_params`
- `::model` properties: `ratio`, `height`, `period`

`NativeSweepRunner` treats this template as read-only. Generated point models
are saved under `jobs\<job_id>\models\`.

## Read-only inventory

After installing the template, run:

```cmd
scripts\windows\inspect_metasurface_template.bat
```

This opens the template with `hide=True` using Lumerical v242 Python and writes
`base_model.inventory.json`. It must not solve, modify, or save the `.fsp`.
Inventory is discovery evidence only and cannot authorize a real run.

## Targeted read-only probe (Stage B0)

After inventory review, run the targeted probe to resolve object identity,
source strategy, and verify real property names:

```cmd
scripts\windows\probe_metasurface_template.bat
```

This writes `base_model.probe.json` (git-ignored). The probe must not solve,
modify, or save the `.fsp`. Probe output cannot authorize a real run.

See `SOP-011` for the full Stage B0 workflow.

## Stage B1 strict profile

`template-inspection-profile.json` is the git-tracked strict contract profile.
It records the exact canonical paths and solver evidence found by Stage B0.1.
`base_model.contract.json` is generated at runtime and remains git-ignored.

The current x/y boundary settings are preserved from evidence:
`Anti-Symmetric` on x and `Symmetric` on y. This is a physics-review warning,
not a contract-generation failure.
