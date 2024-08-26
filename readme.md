### Description

A tool to search words on Win10 by invoking django-mdict.

### Install

1. Install dependencies.

> pip install -r requirements.txt

2. Download model file pytorch_model.bin from [https://huggingface.co/kha-white/manga-ocr-base/tree/main](https://huggingface.co/kha-white/manga-ocr-base/tree/main) and put it in the path django-mdict-tool/data/manga-ocr-base/

3. Run main.py

### Function

* main window is from official example simplebrowser

[https://github.com/qtproject/pyside-pyside-setup/](https://github.com/qtproject/pyside-pyside-setup/)

* screenshot function is from

[https://www.bilibili.com/video/BV1VD4y1b7s5/](https://www.bilibili.com/video/BV1VD4y1b7s5/)

* ocr function is from manga-ocr (suited for reading Japanese manga) and pytesseract

[https://github.com/kha-white/manga-ocr](https://github.com/kha-white/manga-ocr)

[https://github.com/madmaze/pytesseract](https://github.com/madmaze/pytesseract)

* icons are from material-design-icons

[https://github.com/google/material-design-icons](https://github.com/google/material-design-icons)


### Troubleshooting

* importerror: dll load failed while importing fugashi: the specified module could not be found

copy libmecab.dll from C:/Users/YourUserName/AppData/Roaming/Python/lib/site-packages/fugashi to C:/Users/YourUserName/AppData/Roaming/Python/Python310/site-packages/fugashi
