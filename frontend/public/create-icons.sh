#!/bin/bash

# Create 192x192 icon
convert -size 192x192 xc:'#d4a574' -gravity center -pointsize 80 -fill white -annotate +0+0 '₺$€' icon-192.png 2>/dev/null || echo "Creating icon with ImageMagick failed, will use alternative"

# Create 512x512 icon
convert -size 512x512 xc:'#d4a574' -gravity center -pointsize 200 -fill white -annotate +0+0 '₺$€' icon-512.png 2>/dev/null || echo "Creating icon with ImageMagick failed, will use alternative"

# If ImageMagick not available, create simple colored squares
if [ ! -f "icon-192.png" ]; then
  # Create a simple PNG with Python PIL if available
  python3 << 'PYEOF'
from PIL import Image, ImageDraw, ImageFont
import os

try:
    # Create 192x192 icon
    img192 = Image.new('RGB', (192, 192), color='#d4a574')
    draw192 = ImageDraw.Draw(img192)
    try:
        font192 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
    except:
        font192 = ImageFont.load_default()
    text = "₺$€"
    bbox = draw192.textbbox((0, 0), text, font=font192)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (192 - text_width) // 2
    y = (192 - text_height) // 2
    draw192.text((x, y), text, fill='white', font=font192)
    img192.save('icon-192.png')
    
    # Create 512x512 icon
    img512 = Image.new('RGB', (512, 512), color='#d4a574')
    draw512 = ImageDraw.Draw(img512)
    try:
        font512 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
    except:
        font512 = ImageFont.load_default()
    bbox = draw512.textbbox((0, 0), text, font=font512)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (512 - text_width) // 2
    y = (512 - text_height) // 2
    draw512.text((x, y), text, fill='white', font=font512)
    img512.save('icon-512.png')
    
    print("Icons created successfully")
except Exception as e:
    print(f"Error: {e}")
PYEOF
fi
