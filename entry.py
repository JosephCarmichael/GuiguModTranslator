"""Executable entry point; diagnostics are opt-in and make no paid calls by default."""
import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

def main():
    if '--setup-game' in sys.argv:
        from app_config import save_preferences
        from game_setup import validate_game
        game = validate_game(sys.argv[sys.argv.index('--setup-game') + 1])
        save_preferences(game=str(game))
        sys.argv = [sys.argv[0]]
    if '--self-test' in sys.argv or '--self-test-live' in sys.argv:
        from frozen_checks import check
        flag = '--self-test-live' if '--self-test-live' in sys.argv else '--self-test'
        check(sys.argv[sys.argv.index(flag) + 1], live=flag.endswith('-live'))
        return
    from run import main as run_main
    run_main()

if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        from app_config import data_dir
        (data_dir() / 'last-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        if len(sys.argv) == 1:
            from tkinter import messagebox
            messagebox.showerror('Could not start', 'The app could not start. Details were saved in last-error.log in the app data folder.')
        raise SystemExit(1)
