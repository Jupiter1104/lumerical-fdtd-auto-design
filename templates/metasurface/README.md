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
