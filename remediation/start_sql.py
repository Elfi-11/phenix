"""Lance le moteur ML commun actif avec un verrou unique par depot, sur le PC hote."""
from pathlib import Path
import os
import sys


def acquire_lock(path):
    # Le verrou porte sur un descripteur ouvert. Il est libere par l'OS a la
    # sortie du processus, meme si le fichier .lock reste present sur le disque.
    stream = open(path, 'a+b')
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b'0'); stream.flush()
    stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        stream.close()
        raise RuntimeError('Un moteur ML commun automatique utilise deja ce depot') from exc
    return stream


def main():
    # Exiger le secret fourni par start.ps1 : aucun prompt cache ou mot de passe
    # de remplacement lors d'un lancement automatique.
    if not os.environ.get('DEMO_USER_PASSWORD'):
        raise RuntimeError('DEMO_USER_PASSWORD absent : lancer infra/secrets/start.ps1')
    lock = acquire_lock(Path(__file__).with_name('ml-runtime.lock'))
    try:
        # L'import apres le controle permet au moteur de lire l'environnement
        # prepare par PowerShell. Le code du moteur commun reste le point d'entree.
        import moteur_ml
        sys.argv = [str(Path(moteur_ml.__file__)), '--apply']
        moteur_ml.main()
    finally:
        lock.close()


if __name__ == '__main__':
    main()
