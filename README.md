# 🧹 Quick Cleaner (Windows)

A lightweight **Windows desktop cleaner** built with **PySide6** that can quickly remove temporary files, caches, recent items, recycle bin contents, and browser data.  
It includes a **floating widget** with progress display and a **system tray icon** for easy access.

---

## ✨ Features

- 🗑️ **Cleans common junk files**:
  - Recycle Bin  
  - Temp folders (user and Windows)  
  - Recent items list  
  - Windows thumbnail/icon cache  
  - Browser caches (Chrome, Edge, Brave, Vivaldi, Opera, Firefox)  
- 📊 **Real-time cleaning progress bar** with bytes freed.  
- 🚀 **One-click “Clean Now” button**.  
- 🖥️ **System tray integration** with quick menu (Clean / Quit).  
- 🎨 **Modern UI** with shadows, gradients, and rounded corners.  
- 🖱️ **Draggable floating widget** that stays on top of other windows.  

---

## ⚙️ Requirements

- **Windows OS** (tested on Windows 10/11).  
- **Python 3.9+**  
- Dependencies:
  - [PySide6](https://pypi.org/project/PySide6/)  

Install them with:

```bash
pip install PySide6
````

---

## 🚀 Usage

Clone this repository and run:

```bash
python quick_cleaner.py
```

* Click **“Clean Now”** to start cleaning.
* Progress bar will show which step is running and how much has been freed.
* The **system tray icon** gives you quick access:

  * **Clean Now**
  * **Quit**

---

## 🧹 What Gets Cleaned

* **Recycle Bin**
* **Temp folders** (User + optional Windows temp)
* **Recent items** list
* **Windows thumbnail/icon caches** (Explorer rebuilds them automatically)
* **Browser caches**:

  * Chrome
  * Edge
  * Brave
  * Vivaldi
  * Opera
  * Firefox

⚠️ *Windows Temp cleaning is commented out by default for safety (requires admin for full effect). You can enable it by uncommenting in `CLEAN_TASKS`.*

---

## 🔑 Admin vs Non-Admin Mode

Some cleaning tasks require Administrator rights for full access:

* **Without Administrator:**

  * Can clean user-level data (user temp, recent items, browser caches).
  * Limited access to Windows Temp and system-wide caches.

* **With Administrator:**

  * Can clean **system-wide Temp folders** and more deeply remove cached files.
  * Frees up **more space** overall.

👉 For **best results**, run the app as **Administrator**.

---

## 📂 Project Structure

```
quick_cleaner.py   # Main application (widget, tray, cleaning logic)
README.md          # Project documentation
```

---

## 📜 License

MIT License – feel free to use, modify, and share.
