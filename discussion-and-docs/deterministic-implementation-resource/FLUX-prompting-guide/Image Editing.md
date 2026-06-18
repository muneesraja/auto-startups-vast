
Overview of image editing with FLUX.2 — swap backgrounds, replace objects, transfer styles, and combine multi-reference images in natural language.

FLUX.2 brings powerful image editing capabilities across the entire model family. Describe what you want changed in natural language — swap backgrounds, replace objects, transfer styles, adjust lighting — and FLUX.2 makes it happen while maintaining photorealism.All **FLUX.2** variants support multi-reference image editing, allowing you to combine elements from multiple source images into a single coherent result.

![Starting Image](https://cdn.sanity.io/images/2gpum2i6/production/03cb44b883709a79500c46d8db8e0d0fc932413d-1440x1024.png)

A lone wolf standing on a rocky outcropping, bathed in golden light. The wind ruffles its thick grey fur as it gazes across a vast wilderness landscape.

Starting Image

Change the character

Adjust the Composition

Alter the Action

Swap the Setting

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_overview#reference-images-per-model)

Reference Images per Model

|Model|Reference Images (API)|Reference Images (Playground)|
|---|---|---|
|**FLUX.2 [max]**|Up to **8**|Up to **10**|
|**FLUX.2 [pro]**|Up to **8**|Up to **10**|
|**FLUX.2 [flex]**|Up to **8**|Up to **10**|
|**FLUX.2 [klein] 9B**|Up to **4**|—|
|**FLUX.2 [klein] 4B**|Up to **4**|—|
|**FLUX.2 [dev]**|Recommended max **6**|—|

More reference images means more control. Use multiple inputs to maintain character consistency, combine furniture from different photos, or transfer styles — all in a single generation.

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_overview#single-editing-example)

Single Editing Example

Change it to Night

Copy prompt

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_overview#multi-reference-example)

Multi-Reference Example

![Ice Skates](https://cdn.sanity.io/images/2gpum2i6/production/669126258fdc53965be6d8168180b298755d5db1-1125x750.png)

1

![Location](https://cdn.sanity.io/images/2gpum2i6/production/5c022629eb46a126547ea685a5bedb145288875c-1125x750.png)

2

![Decorations](https://cdn.sanity.io/images/2gpum2i6/production/c00b05340b6dc9807e492efa7cd85277d4fc7201-500x331.png)

3

![Result](https://cdn.sanity.io/images/2gpum2i6/production/31acfcff514f52c13abb3a7327d4d74aeb35103c-1120x736.png)

Result

prompt:Create a vintage image taken with a Kodak camera, with heavy grain and slight light smudges. Use Image 2 as the location. Insert only the ice skates from Image 1 into Image 2, with the decorations and evening lighting vibe from Image 3. Add more people skating on the ice.