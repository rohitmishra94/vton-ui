import os
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse
import torch
from PIL import Image
import io
from datetime import datetime
from huggingface_hub import snapshot_download
from model.cloth_masker import AutoMasker
from model.pipeline import CatVTONPipeline
from utils import init_weight_dtype, resize_and_crop, resize_and_padding
from diffusers.image_processor import VaeImageProcessor

app = FastAPI()

# Initialize the model and other components
repo_path = snapshot_download(repo_id='zhengchong/CatVTON')

pipeline = CatVTONPipeline(
    base_ckpt='runwayml/stable-diffusion-inpainting',
    attn_ckpt=repo_path,
    attn_ckpt_version="mix",
    weight_dtype=init_weight_dtype("bf16"),
    use_tf32=True,
    device='cuda'
)

mask_processor = VaeImageProcessor(vae_scale_factor=8, do_normalize=False, do_binarize=True, do_convert_grayscale=True)
automasker = AutoMasker(
    densepose_ckpt=os.path.join(repo_path, "DensePose"),
    schp_ckpt=os.path.join(repo_path, "SCHP"),
    device='cuda', 
)

output_dir = '/workspace/CatVTON/output'

@app.post("/try_on/")
async def try_on(
    person_image: UploadFile = File(...),
    cloth_image: UploadFile = File(...),
    cloth_type: str = Form(...),
):
    # Read and process input images
    person_img = Image.open(io.BytesIO(await person_image.read())).convert("RGB")
    cloth_img = Image.open(io.BytesIO(await cloth_image.read())).convert("RGB")
    
    person_img = resize_and_crop(person_img, (768, 1024))
    cloth_img = resize_and_padding(cloth_img, (768, 1024))
    
    # Generate mask
    mask = automasker(person_img, cloth_type)['mask']
    mask = mask_processor.blur(mask, blur_factor=9)
    
    # Run inference
    result_image = pipeline(
        image=person_img,
        condition_image=cloth_img,
        mask=mask,
        num_inference_steps=50,
        guidance_scale=2.5,
        generator=torch.Generator(device='cuda').manual_seed(42)
    )[0]
    
    # Save and return the result
    date_str = datetime.now().strftime("%Y%m%d%H%M%S")
    result_save_path = os.path.join(output_dir, f"{date_str}.png")
    os.makedirs(output_dir, exist_ok=True)
    result_image.save(result_save_path)
    
    return FileResponse(result_save_path, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)