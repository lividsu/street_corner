import subprocess

def run():
    w, h = 1080, 1920
    cover_box = int(w * 0.65)
    cover_y = int(h * 0.2)
    
    vf = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=60,eq=saturation=1.2:brightness=-0.1[bg];"
        f"[0:v]scale={cover_box}:{cover_box}:force_original_aspect_ratio=decrease[cover];"
        f"[bg][cover]overlay=(W-w)/2:{cover_y}[comp]"
    )
    
    print("VF:", vf)
run()
