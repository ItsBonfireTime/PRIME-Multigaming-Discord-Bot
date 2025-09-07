import subprocess
import sys

def install_package(package):
    """Installiert ein Python-Paket."""
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

if __name__ == "__main__":
    print("Starte die Installation der Abhängigkeiten...")
    install_package("discord.py")
    print("Installation abgeschlossen.")