# NVIDIA Driver Version Requirements for CUDA

## Overview

Vast.ai offers come with varying NVIDIA driver versions. The Docker image `vastai/comfy:v0.20.1-cuda-12.9-py312` requires CUDA 12.9, which needs a compatible host driver.

**Problem:** CUDA 12.9 image fails on hosts with older drivers (e.g., 525.x) with error:
```
RuntimeError: Unexpected error from cudaGetDeviceCount(). Did you run some cuda functions before calling NumCudaDevices() that might have already set an error? Error 804: forward compatibility was attempted on non supported HW
```

## Driver vs CUDA Compatibility

| Driver Version | CUDA Support | Hardware Support |
|----------------|--------------|------------------|
| 525.x | CUDA 12.0 | RTX 30/40 series |
| 535.x | CUDA 12.2 | RTX 30/40 series |
| 550.x | CUDA 12.4 | RTX 30/40 series |
| 560.x | CUDA 12.6 | RTX 30/40 series |
| 570.x | CUDA 12.8 | RTX 30/40 series |
| 580.x | CUDA 13.0 | RTX 40/50 series |

**For CUDA 12.9 (vastai/comfy:v0.20.1):**
- Minimum driver: **560.0.0** (CUDA 12.6 with forward compatibility)
- Recommended: **570.x+** (full CUDA 12.9 support)

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