import tkinter as tk
import threading
import time
import mss
import numpy as np
from pynput.keyboard import Controller, Listener
from PIL import ImageGrab

# ===============================
# CONFIGURATION
# ===============================
lanes = ['A', 'S', 'D', 'F', 'G']
base_coords = {
    'A': ((750, 882), (785, 911)),
    'S': ((842, 888), (880, 916)),
    'D': ((937, 885), (980, 913)),
    'F': ((1035, 884), (1075, 912)),
    'G': ((1128, 887), (1171, 918))
}
THRESHOLD = 18.0
COOLDOWN = 0.20

# ===============================
# GLOBAL STATE
# ===============================
is_running = False
reset_baseline = False
status_text = "PAUSED"
status_color = "red"

# ===============================
# MACRO LOGIC (Background Thread)
# ===============================
def macro_loop():
    global is_running, reset_baseline, status_text, status_color
    
    keyboard = Controller()
    
    # 1. Retina Scale Detection
    try:
        test_img = ImageGrab.grab(bbox=(0, 0, 100, 100))
        RETINA_SCALE = test_img.size[0] / 100
    except:
        RETINA_SCALE = 2.0 # Fallback

    # 2. Setup Coordinates
    all_x1 = [c[0][0] for c in base_coords.values()]
    all_x2 = [c[1][0] for c in base_coords.values()]
    all_y1 = [c[0][1] for c in base_coords.values()]
    all_y2 = [c[1][1] for c in base_coords.values()]

    min_x, max_x = min(all_x1), max(all_x2)
    min_y, max_y = min(all_y1), max(all_y2)

    monitor_area = {
        "left": int(min_x),
        "top": int(min_y),
        "width": int(max_x - min_x),
        "height": int(max_y - min_y)
    }

    lane_slices = {}
    for lane in lanes:
        (lx1, ly1), (lx2, ly2) = base_coords[lane]
        rel_x1 = int((lx1 - min_x) * RETINA_SCALE)
        rel_y1 = int((ly1 - min_y) * RETINA_SCALE)
        rel_x2 = int((lx2 - min_x) * RETINA_SCALE)
        rel_y2 = int((ly2 - min_y) * RETINA_SCALE)
        lane_slices[lane] = (slice(rel_y1, rel_y2), slice(rel_x1, rel_x2))

    prev_frames = {}
    key_held = {k: False for k in lanes}
    last_press_time = {k: 0.0 for k in lanes}

    # 3. Main High-Speed Loop
    with mss.mss() as sct:
        while True:
            # Check toggle state
            if is_running:
                status_text = "RUNNING"
                status_color = "#00ff00" # Bright Green
                
                try:
                    big_img_bgra = np.array(sct.grab(monitor_area))
                    big_img_gray = np.mean(big_img_bgra, axis=2)
                except Exception as e:
                    print(f"Capture error: {e}")
                    continue

                if reset_baseline:
                    for lane in lanes:
                        y_slice, x_slice = lane_slices[lane]
                        prev_frames[lane] = big_img_gray[y_slice, x_slice]
                    reset_baseline = False
                    continue

                if prev_frames:
                    current_time = time.time()
                    for lane in lanes:
                        y_slice, x_slice = lane_slices[lane]
                        current_crop = big_img_gray[y_slice, x_slice]
                        
                        if current_crop.shape != prev_frames[lane].shape:
                            prev_frames[lane] = current_crop
                            continue

                        diff = np.mean(np.abs(current_crop - prev_frames[lane]))

                        if diff > THRESHOLD:
                            if not key_held[lane]:
                                if (current_time - last_press_time[lane]) > COOLDOWN:
                                    keyboard.press(lane.lower())
                                    key_held[lane] = True
                                    last_press_time[lane] = current_time
                        else:
                            if key_held[lane]:
                                if (current_time - last_press_time[lane]) > COOLDOWN:
                                    keyboard.release(lane.lower())
                                    key_held[lane] = False

                        prev_frames[lane] = current_crop
            else:
                status_text = "PAUSED (Press 1)"
                status_color = "red"
                # If paused, ensure keys are released
                for lane, held in key_held.items():
                    if held:
                        keyboard.release(lane.lower())
                        key_held[lane] = False
                time.sleep(0.1)

# ===============================
# KEYBOARD LISTENER (Thread)
# ===============================
def on_press(key):
    global is_running, reset_baseline
    try:
        if hasattr(key, 'char') and key.char == "1":
            is_running = not is_running
            if is_running:
                reset_baseline = True
    except AttributeError:
        pass

# ===============================
# GUI (Main Thread)
# ===============================
def start_gui():
    root = tk.Tk()
    root.title("Macro")
    root.geometry("200x60")
    
    # Keep window on top of everything (even the game)
    root.wm_attributes("-topmost", 1)
    
    # Make the background black
    root.configure(bg='black')

    # Label to show status
    label = tk.Label(root, text="INITIALIZING", font=("Helvetica", 16, "bold"), bg='black', fg='white')
    label.pack(expand=True, fill='both')

    # Function to update GUI from the global variables
    def update_status():
        label.config(text=status_text, fg=status_color)
        root.after(100, update_status) # Run again in 100ms

    # Start Threads
    t = threading.Thread(target=macro_loop, daemon=True)
    t.start()
    
    l = Listener(on_press=on_press)
    l.start()

    # Start GUI Loop
    update_status()
    root.mainloop()

if __name__ == "__main__":
    start_gui()