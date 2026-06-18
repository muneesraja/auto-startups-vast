
Combine multiple input images for style transfer, composites, and editorial scenes

Multi-reference editing combines multiple input images into a single generated output. Use it for fashion composites, interior design, product scenes, and character-consistent variations. When using several references, describe the role of each image so the model knows what to pull from where.

**[pro] API has a 9MP total limit for input + output.** At 1MP output you can use up to 8 reference images, at 2MP output up to 7, and so on. FLUX.2 [klein] supports up to 4 references.

Multi-reference works well for:

- **Fashion shoots**: Combine clothing items into styled outfits
- **Interior design**: Place furniture and decor in rooms
- **Product composites**: Combine multiple products in scenes
- **Character consistency**: Maintain identity across variations

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#example-1)

Example 1

![Chickens](https://cdn.sanity.io/images/2gpum2i6/production/1115a1438ca3daaad5b54b95ea2b174db57b03f4-500x333.png)

1

![Mat A](https://cdn.sanity.io/images/2gpum2i6/production/e27fe799702fe6df233cbf76e44af09f0babe0f6-500x750.png)

2

![Pillow](https://cdn.sanity.io/images/2gpum2i6/production/b215d41ffba47fa273687db0a2c3ba854e8fdf19-500x333.png)

3

![Mat B](https://cdn.sanity.io/images/2gpum2i6/production/dad25402f86c0e338f430679ea7253d38309fd71-421x750.png)

4

![Wood](https://cdn.sanity.io/images/2gpum2i6/production/9606b80fdb30699eef8876d51a2d958b5489f56b-500x333.png)

5

![Eggs](https://cdn.sanity.io/images/2gpum2i6/production/4e3452cf324b7a9a1bd04c46861ba1bbf7d94433-500x333.png)

6

![Result](https://cdn.sanity.io/images/2gpum2i6/production/4bd08e6e18e3ef9dc1a0a153ff304e38f8a4d233-496x320.png)

Result

prompt:Create a house for the chickens from image 1 using materials from images 2, 3, 4, and 5. Use the wood from image 5 for the base, the materials from images 2 and 4 for the walls and floor, and the material from image 3 for a small pillow nest. Place the chickens from image 1 in their new home, sitting on the pillow nest. Next to them, include the eggs from image 6. Apply the style of image 1 to the entire new scene.

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#example-2)

Example 2

![Swing](https://cdn.sanity.io/images/2gpum2i6/production/bb9e891629e8938743b8a68b4ce77290c8ec65c0-2160x2700.jpg)

1

![Woman](https://cdn.sanity.io/images/2gpum2i6/production/b93671c8254ee4e1822195fd0938c08c6ad227ef-1033x1549.jpg)

2

![Cat](https://cdn.sanity.io/images/2gpum2i6/production/d25f8febe3187a9462d7d82b145b986309de7386-3090x4633.jpg)

3

![Style](https://cdn.sanity.io/images/2gpum2i6/production/63d0711eb27f5f4383a83d4286db94971c71c4c1-736x912.png)

4

![Result](https://cdn.sanity.io/images/2gpum2i6/production/1ef99a1d7b06e57da0facc18ff3ca8b44ced2339-1152x1440.png)

Result

prompt:A photograph of the woman in image 2 sitting on the swing in image 1 and the cat from image 3 sitting on her lap, all in the style of image 4

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#example-3)

Example 3

![View](https://cdn.sanity.io/images/2gpum2i6/production/4914d39ec46fa9cd1878e10674081b3959703694-1033x1549.jpg)

1

![Couple](https://cdn.sanity.io/images/2gpum2i6/production/ba45c02ec73c084540b0801688954e0722c989d9-949x1686.jpg)

2

![Food](https://cdn.sanity.io/images/2gpum2i6/production/9a490f3d6ef69278ffaa972c358c376c37c4e3d0-3848x4810.jpg)

3

![Room](https://cdn.sanity.io/images/2gpum2i6/production/8c547b9eed565e9ef993448ab59ad397aa9689dc-1033x1549.jpg)

4

![Result](https://cdn.sanity.io/images/2gpum2i6/production/3161e52aa3afefd2546633b6d437bebe6f99935c-960x1440.png)

Result

prompt:Place the view from image 1 inside the window of image 4, making it the new background seen through the glass. Then place the couple from image 2 seated naturally at the table in image 4, matching scale, lighting, and perspective. Finally, put the food from image 3 on the table in front of them, arranged so it looks like they are sharing the meal together.

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#use-cases)

Use Cases

Multi-reference editing covers a wide range of creative and professional tasks. Below are the most common categories with real prompt examples.

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#scene-compositing)

Scene Compositing

Combine elements from multiple source images into a single coherent scene.

Animal placed in scene

![Bathtub](https://cdn.sanity.io/images/2gpum2i6/production/35bbfd4cb834b4b441e76c2aba8025a8d85b29f0-1200x800.jpg)

![Alpaca](https://cdn.sanity.io/images/2gpum2i6/production/6d4accd102227c63a70e516d0e5d76b0cf3f5745-960x1200.jpg)

![Result](https://cdn.sanity.io/images/2gpum2i6/production/68d5eefdcd9931d9536b15b26a0505c9ffcc72d5-1200x800.jpg)

Underwater room

![Room](https://cdn.sanity.io/images/2gpum2i6/production/02393cf9968cbf103195b9eb0343c8ab826a1ae2-799x1200.jpg)

![Underwater](https://cdn.sanity.io/images/2gpum2i6/production/eff4cc5d02f21e4ffd09e649445637e806e56d42-900x1200.jpg)

![Result](https://cdn.sanity.io/images/2gpum2i6/production/451bc541700469e4618645a5c887bf5e04a5b183-786x1200.jpg)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#style-&-material-transfer)

Style & Material Transfer

Apply the visual style, texture, or material of one image onto the content of another.

Impasto style transfer

![Cat photo](https://cdn.sanity.io/images/2gpum2i6/production/0cd2bc72448e9be220cd5de5558f2f6b5973441f-699x750.jpg)

![Style](https://cdn.sanity.io/images/2gpum2i6/production/f2779c2086110676494152f9bf4ef7a22d4fd787-360x237.jpg)

![Result](https://cdn.sanity.io/images/2gpum2i6/production/f9ea604a7f73e7e2f4d185d2d83390221e5adbe2-688x736.jpg)

Animal pattern transfer

![Cat](https://cdn.sanity.io/images/2gpum2i6/production/09d279847b8ff443b7214f5eca5db019053c6246-500x750.jpg)

![Pattern source](https://cdn.sanity.io/images/2gpum2i6/production/ab0dfc97c6e7640a73d57b69daee2891e6fecbdc-502x750.jpg)

![Result](https://cdn.sanity.io/images/2gpum2i6/production/e54cc75458e0ad0e4d3da6e1062dd6b22db29a51-496x736.jpg)

Pattern onto plate

![Plate](https://cdn.sanity.io/images/2gpum2i6/production/d39856ac7f347609b515a27949a3a92e43dcc4e2-1200x800.jpg)

![Pattern](https://cdn.sanity.io/images/2gpum2i6/production/baf2e03f89390f6940a5ce2d0f6f3835262efc22-800x1200.jpg)

![Result](https://cdn.sanity.io/images/2gpum2i6/production/d1b7e8fba2fbfa40e4cfe3c32fcedc0721baaaf9-1200x800.jpg)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#object-replacement)

Object Replacement

Replace or fill objects with elements from another reference image.

Fill bottles with liquid

![Bottles](https://cdn.sanity.io/images/2gpum2i6/production/079050c86be377a68dfcfb17f28acc430a93a54d-1200x1200.jpg)

![Liquid](https://cdn.sanity.io/images/2gpum2i6/production/8d0259eee11952faa21e39334ea4acf99da32382-1200x800.jpg)

![Result](https://cdn.sanity.io/images/2gpum2i6/production/e7687996aa1138fbd8a74bc51a555288112c985b-1200x1200.jpg)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#logo-&-branding)

Logo & Branding

Place logos from one image onto objects or scenes in another.

Logo engraved in tree

![Tree](https://cdn.sanity.io/images/2gpum2i6/production/83125b7b2b5fbe84b55c7031b52dadb8a640a1b1-1200x800.jpg)

1

![Logo](https://cdn.sanity.io/images/2gpum2i6/production/6e754bd689a380d5683120d8054185d365b2070a-1200x675.jpg)

2

![Result](https://cdn.sanity.io/images/2gpum2i6/production/14f4a81efe558ffbeeda7e94dbbadd5279be3f4a-1200x800.jpg)

Result

prompt:Engrave the logo from image 2 into the tree trunk in image 1

Smoke shaped as logo

![Smoke](https://cdn.sanity.io/images/2gpum2i6/production/31d47345b8ee244203ff291ed7ca9e33fc19aa96-1200x675.jpg)

1

![Logo](https://cdn.sanity.io/images/2gpum2i6/production/6e754bd689a380d5683120d8054185d365b2070a-1200x675.jpg)

2

![Result](https://cdn.sanity.io/images/2gpum2i6/production/3c30e4c007520b47ed79974d023386b9d4190d04-1200x675.jpg)

Result

prompt:Shape the smoke in image 1 so that it forms the logo from image 2

---

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_multi_reference#writing-effective-multi-reference-prompts)

Writing Effective Multi-Reference Prompts

Be **specific** about what changes and **clear** about the target state. Reference image locations when needed (e.g., “image 1”, “image 2”) and let the references provide visual context.

## Good prompts

- “Add dramatic storm clouds to the sky”
- “Change her dress from blue to deep burgundy”
- “Age this portrait by 30 years”
- “Change image 1 to match the style of image 2”

## Avoid

- “Make it better”
- “Improve the lighting”
- “Make it more professional”
- “Fix the image”