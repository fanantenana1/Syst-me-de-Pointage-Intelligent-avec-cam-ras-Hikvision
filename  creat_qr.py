# Requirements:
# pip install segno

import segno

def create_qr_svg(data: str, filename: str = "qr_aens2a.svg"):
    qr = segno.make(data, error='h')   # correction d'erreur élevée
    # Couleur noire, fond blanc (ou transparent si background=None)
    qr.save(
        filename,
        scale=10,          # facteur de taille
        dark='black',
        light='white',     # utilisez None pour fond transparent
        border=4
    )
    print(f"QR généré: {filename}")

if __name__ == "__main__":
    create_qr_svg("* AENS2A *")
