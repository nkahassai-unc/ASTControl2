# Startup script to run FireCapture.

import subprocess
import tkinter as tk

def run_firecapture(output_box=None):
    """Run the FireCapture script and optionally display output in a GUI box."""
    # Add 755 permissions to the run_fc.sh script to make it executable if it is not already
    subprocess.run(["chmod", "755", "./run_fc.sh"], check=True)

    # Run the FireCapture script
    process = subprocess.Popen(["./run_fc.sh"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    # Print or display output
    if output_box:
        output_box.insert(tk.END, f"Output of FireCapture:\n{stdout}\n")
        if stderr:
            output_box.insert(tk.END, f"Errors:\n{stderr}\n")
        output_box.see(tk.END)
    else:
        print(f"Output of FireCapture:\n{stdout}")
        if stderr:
            print(f"Errors:\n{stderr}")

if __name__ == "__main__":
    run_firecapture()