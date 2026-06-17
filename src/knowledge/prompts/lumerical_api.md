# Lumerical FDTD Python API Quick Reference

## Session Management

```python
import lumapi  # v242 raw API (sys.path includes api/python)

# Start with GUI visible
fdtd = lumapi.FDTD()  # hide=False (default)

# Start headless
fdtd = lumapi.FDTD(hide=True)

# Context manager (auto-close)
with lumapi.FDTD() as fdtd:
    fdtd.addfdtd()
    fdtd.run()

# Manual close
fdtd.close()
```

## Core Commands

| Command | Description |
|---------|-------------|
| `fdtd.addfdtd()` | Add FDTD simulation region |
| `fdtd.addrect()` | Add rectangle structure |
| `fdtd.addcircle()` | Add circle/disk structure |
| `fdtd.addring()` | Add ring structure |
| `fdtd.addpoly()` | Add polygon structure |
| `fdtd.setnamed(name, property, value)` | Set property of named object |
| `fdtd.getnamed(name, property)` | Get property of named object |
| `fdtd.run()` | Run simulation |
| `fdtd.save(path)` | Save .fsp project |
| `fdtd.load(path)` | Load .fsp project |
| `fdtd.getresult(monitor, attribute)` | Get result data |
| `fdtd.getelectric(monitor)` | Get E-field |
| `fdtd.getmagnetic(monitor)` | Get H-field |
| `fdtd.getversion()` | Get Lumerical version |

## Common Materials

| Material | Database Name |
|----------|--------------|
| Silicon | `Si (Silicon) - Palik` |
| Silicon Dioxide | `SiO2 (Glass) - Palik` |
| Silicon Nitride | `Si3N4 (Silicon Nitride) - Phillip` |
| Air | `Air` (or `etch`) |

## FDTD Region Properties

| Property | Description | Typical Value |
|----------|-------------|---------------|
| `dimension` | "2D" or "3D" | "3D" |
| `x_span`, `y_span`, `z_span` | Simulation size | 8e-6, 8e-6, 2e-6 |
| `mesh_accuracy` | 1-8, higher=finer | 2 |
| `simulation_time` | Total time in fs | 1000e-15 |
| `x_min_bc`, `x_max_bc` | Boundary conditions | "PML" |
| `auto_shutoff_min` | Convergence threshold | 1e-5 |

## Monitor Types

| Type | Command | Use Case |
|------|---------|----------|
| Frequency-domain power | `addpower()` | Transmission/reflection |
| Frequency-domain profile | `addprofile()` | Field distribution |
| Frequency-domain field | `adddftmonitor()` | General field monitoring |
| Time-domain | `addtime()` | Time evolution |
| Index | `addindex()` | Refractive index |
| Movie | `addmovie()` | Field animation |
