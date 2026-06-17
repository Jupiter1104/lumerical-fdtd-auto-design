"""
Embedded photonics domain knowledge for FDTD MCP Server.

Provides Agent guidance: device templates, common pitfalls, best practices.
Pattern adapted from COMSOL MCP knowledge/embedded.py.

All functions are plain (testable without MCP), then wrapped with @mcp.tool().
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Device templates — common photonic devices with key parameters
# ---------------------------------------------------------------------------

DEVICE_TEMPLATES = {
    "mmi_1x2": {
        "description": "1x2 MMI splitter — splits input into two equal outputs",
        "typical_platform": "220nm SOI, SiO2 cladding",
        "key_parameters": [
            "mmi_width", "mmi_length", "taper_width", "taper_length",
            "wg_width (typically 450-500nm)", "output_separation",
        ],
        "design_rules": [
            "MMI width = 2 * wg_width + gap → typically 3-6 um",
            "MMI length ≈ (n_eff * W^2) / (2 * lambda_0) — use first self-image",
            "Taper length > 5 um for adiabatic transition",
            "Output separation must be > 3 um to avoid coupling",
        ],
        "typical_fom": {
            "insertion_loss": "< 0.5 dB",
            "imbalance": "< 5% (0.2 dB)",
        },
    },
    "waveguide": {
        "description": "Straight/single-mode waveguide mode analysis",
        "key_parameters": ["wg_width", "wg_height", "wavelength", "polarization"],
        "design_rules": [
            "SOI: 220nm height, 450-500nm width for TE single-mode at 1550nm",
            "Check effective index with FDE before FDTD",
        ],
    },
    "grating_coupler": {
        "description": "Grating coupler for fiber-to-chip coupling",
        "key_parameters": [
            "grating_period", "etch_depth", "duty_cycle", "n_grating",
        ],
        "design_rules": [
            "Period ≈ lambda_0 / (n_eff - sin(theta_fiber))",
            "Typical: 600-700nm period for SOI at 1550nm, 8-10 degree fiber tilt",
            "Etch depth 70-90nm (partial etch) or 220nm (full etch)",
        ],
    },
    "ring_resonator": {
        "description": "Micro-ring resonator for filtering/modulation",
        "key_parameters": ["ring_radius", "gap", "wg_width", "coupling_length"],
        "design_rules": [
            "FSR = lambda^2 / (2*pi*R*n_g) — choose R for desired FSR",
            "Gap 150-250nm for critical coupling in SOI",
            "Q factor ≈ 10^4 - 10^5 typical",
        ],
    },
}

# ---------------------------------------------------------------------------
# Troubleshooting — common Lumerical errors, causes, and solutions
# ---------------------------------------------------------------------------

TROUBLESHOOTING = {
    "save_popup": {
        "causes": ["save() called with a path where file already exists"],
        "solutions": [
            "Use a fixed save path; overwrite is handled by RPC Server",
            "Set model 'save on exit' to 0 to suppress prompts",
        ],
    },
    "monitor_overlap": {
        "causes": [
            "Monitor cross-section larger than waveguide — captures stray fields",
            "Monitor placed at Z position that intersects adjacent structures",
        ],
        "solutions": [
            "Set monitor x_span / y_span to 2-3x the waveguide width (not 10x)",
            "Verify monitor Z position is in a uniform cross-section region",
            "Check power conservation: if T > 1.0, monitors overlap structures",
        ],
    },
    "mesh_divergence": {
        "causes": [
            "Mesh accuracy too high (>=5) for complex 3D geometry",
            "Sharp corners or thin layers causing singularities",
            "PML boundaries too close to structures",
        ],
        "solutions": [
            "Start with mesh accuracy 2; increase only if needed",
            "Add mesh override regions around fine features",
            "Extend simulation span — PML should be at least lambda/2 from structures",
        ],
    },
    "no_convergence": {
        "causes": [
            "Auto-shutoff min too low (e.g., 1e-7)",
            "Simulation time too short for fields to decay",
            "High-Q resonance not fully captured",
        ],
        "solutions": [
            "Set auto-shutoff min to 1e-5 for initial runs",
            "Increase simulation time (default ~1000 fs for 1550nm)",
            "For resonators, use longer time or frequency-domain analysis",
        ],
    },
    "license_error": {
        "causes": [
            "Another FDTD instance already running (single-seat license)",
            "License server not accessible (if floating license)",
        ],
        "solutions": [
            "Stop any existing FDTD sessions (fdtd_session_stop)",
            "Check the license file for single-user licenses",
            "Restart the RPC Server if session state is stale",
        ],
    },
}

# ---------------------------------------------------------------------------
# Best practices — by simulation phase
# ---------------------------------------------------------------------------

BEST_PRACTICES = {
    "geometry": {
        "tips": [
            "Use script-defined parameters for all dimensions (never hardcode)",
            "Build geometry layer by layer: substrate → core → cladding",
            "Use 'mesh order' to resolve overlapping material priorities",
            "Verify geometry in GUI before running — look for gaps or overlaps",
        ],
        "mistakes": [
            "Forgetting to set material for structures (default is etch/vacuum)",
            "Waveguide width defined but not taper transition region",
            "Z-span of 2D monitors accidentally covering waveguide layers above",
        ],
    },
    "mesh": {
        "tips": [
            "Mesh accuracy 2 is sufficient for most SOI waveguide simulations",
            "Add mesh override regions for thin layers (< 50nm) or gaps",
            "Check mesh view in GUI: look for staircasing on curved surfaces",
            "PML uses at least 8 layers; extend simulation span accordingly",
        ],
        "mistakes": [
            "Mesh accuracy 5+ on first run — enormous memory, slow, often unnecessary",
            "Not checking mesh quality on curved surfaces (rings, circles)",
        ],
    },
    "sources": {
        "tips": [
            "Use 'mode' source type for waveguide excitation (not gaussian)",
            "Select the correct mode (TE0/TM0) — check mode profile before running",
            "Source injection axis should be along the waveguide direction",
        ],
        "mistakes": [
            "Gaussian source on a waveguide — excites all modes, results hard to interpret",
            "Source wavelength range too wide — S-parameter extraction gets noisy",
            "Not verifying the source mode profile matches the waveguide mode",
        ],
    },
    "monitors": {
        "tips": [
            "Place frequency-domain monitors at least 1 um away from sources and PML",
            "Use 2D Z-normal monitors for transmission/reflection (cuts cross-section)",
            "Use frequency-domain profile monitors for field visualization",
            "Monitor x/y span = 2-3x core width (not the full simulation span)",
        ],
        "mistakes": [
            "Monitor overlapping with source injection plane — captures source field directly",
            "Monitor at same Z as a structure interface — captures numerical reflections",
        ],
    },
    "results": {
        "tips": [
            "Always check T_max < 1.01 (passive device sanity check)",
            "For MMI/power splitters: compute insertion loss and imbalance",
            "Visualize E-field at the device mid-plane to spot leaks or reflections",
            "Save .fsp and results CSV before closing — data is not recoverable",
        ],
        "mistakes": [
            "Trusting results without sanity checks — always verify with known physics",
            "Comparing dB values without confirming reference (power vs field ratio)",
        ],
    },
}

# ---------------------------------------------------------------------------
# Plain functions (testable without MCP)
# ---------------------------------------------------------------------------


def get_device_template(device_type: str) -> dict:
    """Get design template for a photonic device type."""
    if device_type not in DEVICE_TEMPLATES:
        return {
            "success": False,
            "error": f"Unknown device type: {device_type}",
            "available": list(DEVICE_TEMPLATES.keys()),
        }
    return {"success": True, "device": device_type, **DEVICE_TEMPLATES[device_type]}


def list_device_templates() -> dict:
    """List all available device design templates."""
    return {
        "success": True,
        "devices": [
            {"name": k, "description": v["description"]}
            for k, v in DEVICE_TEMPLATES.items()
        ],
    }


def get_troubleshooting(error_type: str) -> dict:
    """Get troubleshooting guide for a common Lumerical issue."""
    if error_type not in TROUBLESHOOTING:
        return {
            "success": False,
            "error": f"Unknown error type: {error_type}",
            "available": list(TROUBLESHOOTING.keys()),
        }
    return {"success": True, "error_type": error_type, **TROUBLESHOOTING[error_type]}


def get_best_practices(category: str) -> dict:
    """Get best practices for a simulation phase."""
    if category not in BEST_PRACTICES:
        return {
            "success": False,
            "error": f"Unknown category: {category}",
            "available": list(BEST_PRACTICES.keys()),
        }
    return {"success": True, "category": category, **BEST_PRACTICES[category]}


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_knowledge_tools(mcp: FastMCP) -> None:
    """Register photonics knowledge base tools."""

    @mcp.tool()
    def fdtd_device_template(device_type: str) -> dict:
        """
        Get a design template for a specific photonic device type.

        Provides key parameters, design rules, and typical figures of merit.
        Use this BEFORE starting a new device design to understand the parameter
        space and design constraints.

        Available devices:
        - "mmi_1x2": 1x2 MMI power splitter
        - "waveguide": Single-mode waveguide
        - "grating_coupler": Fiber-to-chip grating coupler
        - "ring_resonator": Micro-ring resonator

        Args:
            device_type: Device type name.

        Returns:
            Design template with parameters, rules, and typical specs.
        """
        return get_device_template(device_type)

    @mcp.tool()
    def fdtd_list_devices() -> dict:
        """
        List all available photonic device design templates.

        Returns:
            List of device types with brief descriptions.
        """
        return list_device_templates()

    @mcp.tool()
    def fdtd_troubleshoot(error_type: str) -> dict:
        """
        Get troubleshooting help for common Lumerical simulation errors.

        Error types:
        - "save_popup": Save dialog blocking automation
        - "monitor_overlap": Monitor overlapping structures → inflated power
        - "mesh_divergence": Mesh generation fails or is too slow
        - "no_convergence": Simulation doesn't converge
        - "license_error": License not available or conflict

        Args:
            error_type: Type of error encountered.

        Returns:
            Causes and solutions for the error.
        """
        return get_troubleshooting(error_type)

    @mcp.tool()
    def fdtd_best_practices(category: str) -> dict:
        """
        Get best practices for a specific simulation phase.

        Categories:
        - "geometry": Geometry creation and material assignment
        - "mesh": Mesh settings and refinement
        - "sources": Source configuration (mode, gaussian, etc.)
        - "monitors": Monitor placement and sizing
        - "results": Result verification and sanity checks

        Args:
            category: Simulation phase to get guidance for.

        Returns:
            Best practices tips and common mistakes.
        """
        return get_best_practices(category)
