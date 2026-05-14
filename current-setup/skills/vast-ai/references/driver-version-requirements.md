# NVIDIA Driver Version Requirements for CUDA

## Overview

Vast.ai offers come with varying NVIDIA driver versions. The Docker image `vastai/comfy:v0.20.1-cuda-12.9-py312` requires CUDA 12.9, which needs a compatible host driver.

**Problem:** CUDA 12.9 image fails on hosts with older drivers (e.g., 525.x) with error:
```
RuntimeError: Unexpected error from cudaGetDeviceCount(). Did you run some cuda functions before calling NumCudaDevices() that might have already set an error? Error 804: forward compatibility was attempted on non supported HW
```

## Driver vs CUDA Compatibility

| Driver Version | CUDA Support | Hardware Support | Notes |
|----------------|--------------|------------------|-------|
| 525.x | CUDA 12.0 | RTX 30/40 series | ❌ Too old for CUDA 12.9 |
| 535.x | CUDA 12.2 | RTX 30/40 series | ❌ Too old for CUDA 12.9 |
| 550.x | CUDA 12.4 | RTX 30/40 series | ❌ Too old for CUDA 12.9 |
| 560.x | CUDA 12.6 | RTX 30/40 series | ❌ Too old - fails with CUDA 12.9 |
| 565.x | CUDA 12.7 | RTX 30/40 series | ⚠️ May work - test needed |
| 570.x | CUDA 12.8 | RTX 30/40 series | ✅ Works (may need compat lib fix) |
| 580.x | CUDA 13.0 | RTX 40/50 series | ✅ **RECOMMENDED** - native support |
| 590.x | CUDA 13.1 | RTX 40/50 series | ✅ Native support |

**For CUDA 12.9 (vastai/comfy:v0.20.1):**
- Minimum driver: **570.0.0** (CUDA 12.8 + forward compat layer)
- Recommended: **580.x+** (CUDA 13.0 native - NO WORKAROUND NEEDED)
- Avoid: **≤565.x** (compat layer conflicts with CUDA 12.9)
- If driver 570.x fails with CUDA Error 804: remove compat libs: `rm -f /usr/local/cuda-12.9/compat/libcuda.so* && ldconfig`

## CUDA Version Filter

Vast.ai exposes `cuda_max_good` in offers — this is the **GPU hardware capability**, NOT the driver's supported CUDA version.

```bash
# ❌ WRONG - cuda_max_good is hardware capability, not driver version
vastai search offers 'cuda_max_good>=12.9'  # Doesn't filter driver!

# ✅ CORRECT - filter by driver version
vastai search offers 'driver_version>=570.0.0'
```

**Critical distinction:**
- `driver_version` — actual NVIDIA driver on host ("580.126.09")
- `cuda_max_good` — GPU hardware capability (3090 shows 12.8 or 13.0)
- A host can have `cuda_max_good: 13.0` (GPU capability) but `driver_version: 525.x` (only supports CUDA 12.0)

**Search filter for CUDA 12.9 image:**
```bash
# Both filters needed for safety
vastai search offers 'gpu_name=RTX_3090 driver_version>=570.0.0 cuda_max_good>=12.8'
```

## Vast.ai Search Filter

The `driver_version` field is available in offers. Filter format requires `X.X.X` version string:

```bash
# Correct format (X.X.X)
vastai search offers 'gpu_name=RTX_3090 driver_version>=560.0.0'

# Wrong format (causes error)
vastai search offers 'gpu_name=RTX_3090 driver_version>=560'  # Fails!
vastai search offers 'gpu_name=RTX_3090 driver_vers>=560000000'  # Fails!
```

**Available fields in offers:**
- `driver_version` — string format "580.126.09" (use `>=560.0.0`)
- `driver_vers` — numeric format 580126009 (not filterable)
- `cuda_max_good` — hardware capability (12.0, 13.0, etc.) — NOT driver version

**Important:** `cuda_max_good` is the GPU's compute capability, NOT the driver's CUDA version. A 3090 shows `cuda_max_good: 13.0` even with driver 525.x (which only supports CUDA 12.0).

## Implementation

### In GPU Profiles

```python
GPU_PROFILES = {
    "3090": {
        ...
        "driver_min": "560.0.0",  # Required for CUDA 12.9
        ...
    },
}
```

### In Search Query

```python
query = (
    f"gpu_name={profile['name']} "
    f"num_gpus=1 "
    f"rented=False "
    f"driver_version>={profile['driver_min']}"  # Filter out old drivers
)
```

### Verifying Driver Version

After provisioning, verify CUDA works:
```bash
python -c "import torch; print(f'CUDA {torch.version.cuda}')"  # Should print CUDA 12.x
```

If it fails with error 804, destroy the instance and mark host as failed.

## Historical Context

- 2026-05-13: Instance 36686102 failed with CUDA driver error — host had driver 525.x
- Root cause: `cuda_max_good` filtered for hardware capability (12.7+), but host driver was 525.06 (CUDA 12.0)
- Docker image CUDA 12.9 requires forward compatibility layer unavailable on old drivers

## Related Files

- `vastai-provision.py` — `driver_min` in GPU_PROFILES, `driver_version` filter in search_offers()
- `failed_hosts.json` — Hosts marked as failed after CUDA errors

## References

- NVIDIA CUDA Compatibility: https://docs.nvidia.com/deploy/cuda-compatibility/
- Vast.ai Search Fields: `vastai search offers --help`