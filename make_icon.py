from PIL import Image, ImageDraw

size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, size - 8, size - 8), radius=size // 4, fill=(76, 194, 255, 255))
d.polygon([(size * .38, size * .28), (size * .38, size * .72), (size * .74, size * .5)], fill=(255, 255, 255, 255))
img.save("wallura.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wallura.ico erstellt")
