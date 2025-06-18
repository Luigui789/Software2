import os
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
creds_path = os.path.join(BASE_DIR, "mycreds.txt")
#==============================================================
print(f"Ruta esperada para mycreds.txt: {creds_path}")

gauth = GoogleAuth()
gauth.LoadCredentialsFile(creds_path)
if gauth.credentials is None:
    gauth.LocalWebserverAuth()
    gauth.SaveCredentialsFile(creds_path)
elif gauth.access_token_expired:
    gauth.Refresh()
    gauth.SaveCredentialsFile(creds_path)
else:
    gauth.Authorize()
    gauth.SaveCredentialsFile(creds_path)

drive = GoogleDrive(gauth)