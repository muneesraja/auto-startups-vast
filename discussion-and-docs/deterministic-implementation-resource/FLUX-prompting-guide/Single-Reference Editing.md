
How to edit images using a single reference with FLUX.2

Single-reference editing is the most common workflow: you provide **one input image** and describe the changes you want. FLUX.2 understands the context of your image and applies edits while preserving what you didn’t ask to change.

Refer to the [Image Editing Overview](https://docs.bfl.ai/guides/prompting_editing_overview) for core concepts before diving into specific use cases.

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#example-1)

Example 1

Change it to Night

Copy prompt

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#example-2)

Example 2

On the top polaroid photo, diagonally, write in handwritten pink marker: "2020 <3"

Copy prompt

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#example-3)

Example 3

Place this can on top of a minimalistic black shiny surface on black background

Copy prompt

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#use-cases)

Use Cases

Single-reference editing covers a wide range of creative and professional tasks. Below are the most common categories with real prompt examples.

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#background-replacement)

Background Replacement

Change or replace the background of your image while keeping the subject intact.

Product on new background

![Input: bottle product photo](https://cdn.sanity.io/images/2gpum2i6/production/40f4afc4e8663ce9087e66d998ca5fed48860a03-600x600.webp)

![Output: bottle in strawberries on white background](https://cdn.sanity.io/images/2gpum2i6/production/5950af13503a110628744a4fe1fb3fff7cbf5a73-1024x1024.png)

Scene replacement

![Input: subject with original background](https://cdn.sanity.io/images/2gpum2i6/production/f0d1483a17bec23427792d50abed3e3579d0d8e1-752x1360.png)

![Output: subject in cozy home environment](https://cdn.sanity.io/images/2gpum2i6/production/881c68c1e53a44d57fbdd84d7b64820b11a34b24-752x1360.png)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#style-transfer)

Style Transfer

Transform the visual style or medium of an image — from illustration to photorealism, or from photo to painting.

Photo to oil painting

![Input: original photo](https://cdn.sanity.io/images/2gpum2i6/production/ef75babb2f3e56a3e4acef468fa5bac88a5e672f-656x736.png)

![Output: oil painting style](https://cdn.sanity.io/images/2gpum2i6/production/aec799c192472171eeac5da0be614ca865bc76c2-656x736.png)

Illustration to photorealism

![Input: architectural illustration](https://cdn.sanity.io/images/2gpum2i6/production/5298b857f3f80c33dc6eb0c69e11a94234a76267-1000x639.jpg)

![Output: photorealistic house](https://cdn.sanity.io/images/2gpum2i6/production/90fe9dafd99234d2a16e0efecdc0e04c7cedff6c-992x624.png)

Reskin to mountain vista

![Input: abstract artwork](https://cdn.sanity.io/images/2gpum2i6/production/00f3de86b945fb15ebf80fedb73bf25613a6cc63-627x1115.jpg)

![Output: mountain vista transformation](https://cdn.sanity.io/images/2gpum2i6/production/ff9926cc9f8fda72cef2423a74bb8837aa2a1b42-624x1104.jpg)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#object-manipulation)

Object Manipulation

Add, remove, or replace objects in a scene. Be specific about what should change and what should stay.

Remove object

![Input: image with sprinkles](https://cdn.sanity.io/images/2gpum2i6/production/9cb1c9770442822cf7ee63402d80f6a002099421-4190x2796.jpg)

![Output: sprinkles removed](https://cdn.sanity.io/images/2gpum2i6/production/2136a5de05310685e6123c9b6851444cb3594c98-1440x960.png)

Remove all of the sprinkles while keeping the rest of the image unchanged

Copy prompt

Replace object

![Input: image with flower](https://cdn.sanity.io/images/2gpum2i6/production/e163342d136d60e1eeea536cfc2ee6fc71b9ce4d-496x736.png)

![Output: flower replaced with lemon slice](https://cdn.sanity.io/images/2gpum2i6/production/1bf1dc0a4964f33fc848c9a7852cfef8ca17ad3a-496x736.png)

Replace the flower in image 1 with a slice of lemon

Copy prompt

Add object

![Input: gorge scene](https://cdn.sanity.io/images/2gpum2i6/production/df06372ee169f763ad923dee2ee8ddd0c60b9d65-496x736.png)

![Output: goblins added to gorge wall](https://cdn.sanity.io/images/2gpum2i6/production/5b64c3f4c5c0e17aacd975118939285d33c833c1-496x736.png)

Replace subject

![Input: DJ scene](https://cdn.sanity.io/images/2gpum2i6/production/20f94b47aeaeaaed370031ca98aed4ba67dc603f-2238x1500.png)

![Output: polar bear replaces DJ](https://cdn.sanity.io/images/2gpum2i6/production/e2d2e556d0ad7a587589e01607febda7dd549785-1440x960.png)

Replace the DJ with a polar bear without headphones

Copy prompt

Selective replacement

![Input: jars with cherries](https://cdn.sanity.io/images/2gpum2i6/production/700fcf1730b96165452bef99fa3f699e256bba45-1024x1024.png)

![Output: cherries replaced with sprinkles](https://cdn.sanity.io/images/2gpum2i6/production/d15d465e7d2807c50efecac83b87f132b9d03c12-1024x1024.png)

Remove vegetation

![Input: moss-covered statues](https://cdn.sanity.io/images/2gpum2i6/production/36a9166aecd1e04f684c9d1fcecb8d78d0338a81-1033x1549.jpg)

![Output: clean stone statues](https://cdn.sanity.io/images/2gpum2i6/production/3e6fd95cb7eb09f98ac4607292ae027c67f215a8-1072x1920.png)

Object swap — bike to horse

![Input: person on motorcycle](https://cdn.sanity.io/images/2gpum2i6/production/59fdd6b45c1d2d4180390ae98380a9425ce8bd99-765x956.jpg)

![Output: person on rearing black horse](https://cdn.sanity.io/images/2gpum2i6/production/95be0d8eeab9acdd7cdfb73d68120385050b7073-752x944.jpg)

Replace the bike with a rearing black horse

Copy prompt

Element replacement — feathers to petals

![Input: portrait with feathers](https://cdn.sanity.io/images/2gpum2i6/production/479b03e2cc5bbdf7f56151ec6dce055cb7dfe11a-688x1028.jpg)

![Output: portrait with rose petals](https://cdn.sanity.io/images/2gpum2i6/production/3cc63c124d2a504a6f1e021948bc69db41b05731-688x1024.jpg)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#color-&-material-changes)

Color & Material Changes

Recolor specific elements or transform materials — FLUX.2 supports hex color codes for precision.

Recolor with hex codes

![Input: cow with natural colors](https://cdn.sanity.io/images/2gpum2i6/production/e42c9778a28707cc65bf7c913591d947f8bfd4b9-500x750.png)

![Output: cow with custom colors](https://cdn.sanity.io/images/2gpum2i6/production/691a310bf2729d3ce4f4bda0402259c3668ca135-928x1024.png)

Change the cow's white fur to the color #8bc4bb and its black spots to #de4528

Copy prompt

Material transformation — silver

![Input: butterfly](https://cdn.sanity.io/images/2gpum2i6/production/ce6665b32fd9f96a2c1bb8bd30e73b000912d225-960x1440.png)

![Output: silver butterfly](https://cdn.sanity.io/images/2gpum2i6/production/d8b6455ab9ab2ee12c914be6afa4bea3fcc414b3-960x1440.png)

Material transformation — ice

![Input: butterfly](https://cdn.sanity.io/images/2gpum2i6/production/649bd0775125f412f8aa0446f55d74f3f1fc1b14-960x1440.png)

![Output: ice butterfly](https://cdn.sanity.io/images/2gpum2i6/production/71a57f1289d5c4934a9e5a1de2d65e490537e271-960x1440.png)

Turn the butterfly into one sculpted from clear ice, with tiny droplets forming across its frozen surface. Create a refined, realistic texture, preserving the original style of the image

Copy prompt

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#lighting-weather-&-season-changes)

Lighting, Weather & Season Changes

Shift the time of day, season, or weather conditions with a simple instruction.

Season change — winter

![Input: scene in original season](https://cdn.sanity.io/images/2gpum2i6/production/60c0bd0873dce1991931829d93ca1270dd42cb0c-1680x952.png)

![Output: winter scene](https://cdn.sanity.io/images/2gpum2i6/production/afd7679c6592a45b2124416faf572ce48c6e114a-1440x816.png)

Time of day — night

![Input: daytime scene](https://cdn.sanity.io/images/2gpum2i6/production/899402d052604cc5471942e61176309b75d8096d-2048x1440.png)

![Output: nighttime scene](https://cdn.sanity.io/images/2gpum2i6/production/31799e6fc25fae11adc720693c4a7bbbc1b9ddb7-1440x1008.png)

Change it to Night

Copy prompt

Lighting and color mood

![Input: scene with original lighting](https://cdn.sanity.io/images/2gpum2i6/production/989d574adc3c3c845a52fadda2d7ae0a15841b73-592x736.png)

![Output: warm autumn lighting](https://cdn.sanity.io/images/2gpum2i6/production/c828dbe1430f5782adfa8610c01a8a87574479bb-592x736.png)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#text-editing)

Text Editing

Add, replace, or modify text within images — from simple swaps to full ad layouts.

Simple text replacement

![Input: image with original text](https://cdn.sanity.io/images/2gpum2i6/production/454286fa6880e6a2772ea1423e478280469354fb-1999x3000.jpg)

![Output: text changed to Flux.2](https://cdn.sanity.io/images/2gpum2i6/production/db0aa37eb019d14345f3bc7593c7caedee5f7fce-944x1440.png)

Neon sign text

![Input: neon sign with original text](https://cdn.sanity.io/images/2gpum2i6/production/7a9cbb845dd15f4c25045d5bdd601ffda9e15b64-1424x944.png)

![Output: neon sign with new text](https://cdn.sanity.io/images/2gpum2i6/production/416e69a864c5eeaf59dd61b992592d47780be3f5-1424x944.png)

Sign replacement + scene edit

![Input: shop scene](https://cdn.sanity.io/images/2gpum2i6/production/865cc685167fa3b10e722a2d048b89cdbf9a9613-752x1440.png)

![Output: new neon sign and traffic light](https://cdn.sanity.io/images/2gpum2i6/production/e228384f2f234290699e684e5a743ebfab7ce38e-752x1440.png)

Ad creation with text overlay

![Input: fashion photo](https://cdn.sanity.io/images/2gpum2i6/production/cc46de090b61254fad1f7c6783b8bb76d05c4ee6-500x750.png)

![Output: fashion ad with text and CTA](https://cdn.sanity.io/images/2gpum2i6/production/7dca5c2b3834bfa11c2bc19051185579c999a380-496x736.png)

Use this image to create an ad. Add the text 'Black Friday hasta -50%' on the right side, making sure it does not overlay the clothes. Add a call-to-action button that says 'Take me there'

Copy prompt

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#virtual-try-on-&-clothing)

Virtual Try-On & Clothing

Change outfits, add accessories, or adjust clothing colors — great for fashion and e-commerce.

Outfit change

![Input: woman in original outfit](https://cdn.sanity.io/images/2gpum2i6/production/6579b7ebe92a74bd1751a3a1cc326ae22913b32b-1033x1549.jpg)

![Output: woman in fuchsia dress](https://cdn.sanity.io/images/2gpum2i6/production/31c55b96ace2a539043fabf95f386ff3e27a6e22-1072x1920.png)

Add accessories with hex colors

![Input: woman without jacket](https://cdn.sanity.io/images/2gpum2i6/production/a4867991ad1e38d17cd89effc5d8b61b96d57f8b-501x750.png)

![Output: woman with fluffy jacket and hat](https://cdn.sanity.io/images/2gpum2i6/production/931e7c71fac23775c0ee893dba5c88cd95ae0b85-496x736.png)

Dress recoloring with detail preservation

![Input: white lace wedding dress](https://cdn.sanity.io/images/2gpum2i6/production/bb82e82e1bdc520dbe56f745d7747ddc60a26760-3456x5184.jpg)

![Output: sky blue lace wedding dress](https://cdn.sanity.io/images/2gpum2i6/production/29a25e49a0f1f5d563c5cc0e6721b763351f6452-960x1440.png)

---

### 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#pose-&-expression-changes)

Pose & Expression Changes

Adjust gaze direction, body pose, or facial expressions of subjects.

Eye/detail correction

![Input: owl with closed eyes](https://cdn.sanity.io/images/2gpum2i6/production/3cf7be64ed894bed4e5dad2ffc1b88962a5e086f-1776x1780.jpg)

![Output: owl with open eyes](https://cdn.sanity.io/images/2gpum2i6/production/d93ac086cafa5884dad80c4c13f6009455225609-1408x1408.png)

Gaze direction

![Input: woman looking away](https://cdn.sanity.io/images/2gpum2i6/production/f4cc0e2d6f1b37a40176de36b1afb03270cbc487-1120x736.png)

![Output: woman looking at camera](https://cdn.sanity.io/images/2gpum2i6/production/1f3ffbe5abba7d217bf410216ca292ab8a002ee0-1120x736.png)

Pose change

![Input: woman in casual pose](https://cdn.sanity.io/images/2gpum2i6/production/c7e90ee8f22b9d2d807375b4fb56278c4909504c-1072x1920.png)

![Output: woman in model pose](https://cdn.sanity.io/images/2gpum2i6/production/4302b878aa72db273183e06d4ed46fe4388647d9-1072x1920.png)

---

## 

[​

](https://docs.bfl.ai/guides/prompting_editing_single_reference#writing-effective-single-reference-prompts)

Writing Effective Single-Reference Prompts

Be **specific** about what changes and **explicit** about what should stay the same. The more precise your instruction, the better the result.

## Good prompts

- “Change the shirt color to red”
- “Replace the background with a sunset beach”
- “Turn this into an oil painting”
- “Add snow to the scene, keep everything else unchanged”

## Avoid

- “Make it better”
- “Improve the lighting”
- “Make it more professional”
- “Fix the image”