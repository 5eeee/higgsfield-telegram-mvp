"""Probe Kling/Minimax motion support + test dual-frame patterns."""
import asyncio, aiohttp, json, time, sys, io
from pathlib import Path
from dotenv import load_dotenv; load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from src.config import load_settings
from src.higgsfield_api import HiggsfieldAPI

async def main():
    s = load_settings()
    api = HiggsfieldAPI(auth_header=s.hf_auth_header, request_timeout_seconds=60, upload_timeout_seconds=120)
    face_url = await api.upload_image_bytes(Path('smoke_face.jpg').read_bytes(), 'image/jpeg')
    print('uploaded face:', face_url[:80])

    h = {'Authorization': s.hf_auth_header, 'Accept':'application/json', 'Content-Type':'application/json'}
    async with aiohttp.ClientSession() as ses:
        # 1. Kling + motions field
        print('\n=== Kling with motion ===')
        async with ses.post('https://platform.higgsfield.ai/v1/image2video/kling',
            headers=h, json={'params':{
                'input_image':{'type':'image_url','image_url':face_url},
                'prompt':'cinematic person running',
                'model':'kling-v2-1','duration':5,
                'motions':[{'id':'dc8d7d9c-ae0c-45fc-b780-7d470b171b45','strength':0.8}],
            }}) as r:
            print('POST:', r.status, (await r.text())[:300])

        # 2. Kling with input_image_end (dual frame)
        print('\n=== Kling with input_image_end ===')
        async with ses.post('https://platform.higgsfield.ai/v1/image2video/kling',
            headers=h, json={'params':{
                'input_image':{'type':'image_url','image_url':face_url},
                'input_image_end':{'type':'image_url','image_url':face_url},
                'prompt':'cinematic zoom transition',
                'model':'kling-v2-1','duration':5,
            }}) as r:
            print('POST:', r.status, (await r.text())[:300])

        # 3. Minimax with motion
        print('\n=== Minimax with motion ===')
        async with ses.post('https://platform.higgsfield.ai/v1/image2video/minimax',
            headers=h, json={'params':{
                'input_image':{'type':'image_url','image_url':face_url},
                'prompt':'cinematic action',
                'duration':6,'resolution':'768',
                'motions':[{'id':'dc8d7d9c-ae0c-45fc-b780-7d470b171b45','strength':0.8}],
            }}) as r:
            print('POST:', r.status, (await r.text())[:300])

        # 4. DoP dual-frame with random UUID face=start, face=end (will it render?)
        print('\n=== DoP dual frame (Zoom In motion) ===')
        # Zoom In motion UUID - need to find from motions_full.json
        mots = json.load(open('motions_full.json','r',encoding='utf-8'))
        zoom_in_id = next(m['id'] for m in mots if m['name'] == 'Zoom In')
        print('Zoom In motion id:', zoom_in_id)

        async with ses.post('https://platform.higgsfield.ai/v1/image2video/dop',
            headers=h, json={'params':{
                'input_images':[{'type':'image_url','image_url':face_url}],
                'input_images_end':[{'type':'image_url','image_url':face_url}],
                'prompt':'cinematic zoom in',
                'model':'dop-preview','duration':5,
                'motions':[{'id':zoom_in_id,'strength':0.8}],
                'enhance_prompt':False,
            }}) as r:
            data = await r.json(content_type=None)
            print('POST:', r.status, json.dumps(data)[:300])

asyncio.run(main())
