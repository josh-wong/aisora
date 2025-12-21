import os
import json
import time
import base64
import shutil
import tempfile
import subprocess
from pathlib import Path
from PIL import Image, UnidentifiedImageError
import io
import re

def find_attachment_files(attachment_id, signal_cli_data_path=None):
    """
    Find attachment files based on attachment ID.
    
    signal-cli stores attachments in its data directory, 
    typically under ~/.local/share/signal-cli/attachments/
    """
    # Determine the signal-cli data path if not provided.
    if not signal_cli_data_path:
        home = os.path.expanduser("~")
        signal_cli_data_path = os.path.join(home, ".local", "share", "signal-cli")
    
    # Attachments are typically stored in the attachments directory.
    attachments_dir = os.path.join(signal_cli_data_path, "attachments")
    
    if not os.path.exists(attachments_dir):
        print(f"Attachments directory not found at: {attachments_dir}")
        return None
    
    print(f"Looking for attachment {attachment_id} in {attachments_dir}")
    
    # Search for files matching the attachment_id pattern.
    found_files = []
    for root, dirs, files in os.walk(attachments_dir):
        for filename in files:
            if attachment_id in filename:
                full_path = os.path.join(root, filename)
                found_files.append(full_path)
                print(f"Found matching attachment file: {full_path}")
    
    if not found_files:
        print(f"No files found for attachment ID: {attachment_id}")
        return None
    
    # Return the first matching file.
    return found_files[0]

def process_image_file(image_path):
    """Attempt to process an image file for Llama models that support vision"""
    try:
        print(f"Processing image file: {image_path}")
        
        # Check if the file exists.
        if not os.path.exists(image_path):
            print(f"Error: Image file not found at {image_path}")
            return None
        
        # Check the file size.
        file_size = os.path.getsize(image_path)
        print(f"Image file size: {file_size} bytes")
        if file_size == 0:
            print("Error: Empty file")
            return None
        
        # Try to open with PIL to validate if it's a proper image.
        try:
            with Image.open(image_path) as img:
                print(f"Valid image detected: {img.format}, Size: {img.size}")
                
                # Only resize if the image is very large.
                if max(img.size) > 4096:
                    print(f"Resizing large image of {max(img.size)}px")
                    # Maintain the aspect ratio.
                    img.thumbnail((4096, 4096))
                
                # If image has alpha channel (RGBA mode), convert to RGB before saving as JPEG
                if img.mode == 'RGBA':
                    print("Converting RGBA image to RGB mode for JPEG compatibility")
                    # Create a new RGB image with white background
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    # Paste the image on the background using alpha as mask
                    rgb_img.paste(img, mask=img.split()[3])  # 3 is the alpha channel
                    img = rgb_img
                
                # Save to a byte buffer.
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=90)
                buffer.seek(0)
                
                # Convert to base64.
                encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
                mime_type = "image/jpeg"
                
                print(f"Successfully encoded image. Base64 length: {len(encoded_image)}")
                
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": encoded_image
                    }
                }
        except UnidentifiedImageError:
            print(f"Error: Not a valid image file: {image_path}")
            return None
        
    except Exception as e:
        print(f"Error processing image: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_attachment_id_from_signal_response(message_line):
    """
    Extract attachment ID from a Signal message response.
    This helps identify the attachment ID pattern in error messages.
    """
    try:
        # Try common patterns in the signal-cli output.
        patterns = [
            r'[_\-0-9a-zA-Z]+\.(jpg|jpeg|png|gif)', # Common filename patterns
            r'attachment ID: ([_\-0-9a-zA-Z]+)', # Explicit ID in message
            r'Failed to download attachment ID: ([_\-0-9a-zA-Z]+)' # Error message format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message_line, re.IGNORECASE)
            if match:
                if '.' in match.group():
                    # If the filename is matched, get just the filename part.
                    return os.path.splitext(match.group())[0]
                else:
                    # Otherwise, get the capture group.
                    return match.group(1) if len(match.groups()) > 0 else match.group()
                    
        return None
    except Exception as e:
        print(f"Error extracting attachment ID: {e}")
        return None

def download_attachment_with_cli(attachment_id):
    """
    Alternative method to download an attachment using direct signal-cli command.
    This is a fallback method that uses subprocess to call signal-cli directly.
    """
    try:
        # Create a temp directory for the attachment.
        temp_dir = tempfile.mkdtemp()
        print(f"Created temp directory for attachment: {temp_dir}")
        
        # Call signal-cli directly to receive messages with the attachment output.
        cmd = ["signal-cli", "--output", temp_dir, "receive", "--timeout", "1"]
        print(f"Running command: {' '.join(cmd)}")
        
        # Run the command.
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"Command output: {result.stdout}")
        
        # Look for files in the output directory.
        for root, dirs, files in os.walk(temp_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                if os.path.getsize(file_path) > 0:
                    print(f"Found file: {file_path}, size: {os.path.getsize(file_path)} bytes")
                    return file_path
        
        print(f"No valid files found in {temp_dir}")
        return None
    except Exception as e:
        print(f"Error in download_attachment_with_cli: {e}")
        return None

def get_attachment(attachment_id, proc=None):
    """
    Comprehensive function to get an attachment using multiple methods.
    Tries different approaches to locate and process the attachment.
    """
    # First, try to find the file directly in the signal-cli data directory.
    attachment_path = find_attachment_files(attachment_id)
    if attachment_path:
        return attachment_path
        
    # If not found, try the direct CLI method.
    if not attachment_path:
        print("Trying alternative CLI method to download attachment")
        attachment_path = download_attachment_with_cli(attachment_id)
        if attachment_path:
            return attachment_path
    
    # If there's a JSON-RPC process, try using it.
    if not attachment_path and proc:
        try:
            # Try by using the JSON-RPC receive method.
            temp_dir = tempfile.mkdtemp()
            
            json_request = {
                "jsonrpc": "2.0",
                "method": "receive",
                "params": {
                    "timeout": 1,
                    "returnOnTimeout": True,
                    "output": temp_dir
                },
                "id": str(int(time.time()))
            }
            
            json_str = json.dumps(json_request) + "\n"
            proc.stdin.write(json_str)
            proc.stdin.flush()
            print(f"Sent receive request with output directory: {temp_dir}")
            
            # Wait a moment for potential downloads.
            time.sleep(2)
            
            # Look for files.
            for root, dirs, files in os.walk(temp_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    if os.path.getsize(file_path) > 0:
                        print(f"Found file via JSON-RPC: {file_path}")
                        return file_path
        except Exception as e:
            print(f"Error in JSON-RPC attachment attempt: {e}")
    
    print(f"All attachment retrieval methods failed for ID: {attachment_id}")
    return None

def describe_image_with_text(image_path):
    """
    Generate a text description of an image for Llama models that don't support vision.
    This is a fallback method that provides basic image information.
    """
    try:
        if not os.path.exists(image_path):
            return "Error: Image file not found."
        
        with Image.open(image_path) as img:
            # Get basic image information
            format_name = img.format
            size = img.size
            mode = img.mode
            
            # Calculate approximate file size
            file_size = os.path.getsize(image_path)
            file_size_mb = file_size / (1024 * 1024)
            
            description = f"I can see that you've shared an image with me. Here are the technical details I can provide:\n\n"
            description += f"• Format: {format_name}\n"
            description += f"• Dimensions: {size[0]} × {size[1]} pixels\n"
            description += f"• Color mode: {mode}\n"
            description += f"• File size: {file_size_mb:.2f} MB\n\n"
            description += "Unfortunately, I'm a text-based AI model and cannot analyze the visual content of images. "
            description += "If you'd like to discuss the image, please describe what you'd like to know about it, "
            description += "or provide a description of what the image contains."
            
            return description
            
    except Exception as e:
        return f"Error processing image: {str(e)}"
