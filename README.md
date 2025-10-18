# gtpmatch

Lightweight Python library for running games between Go bots using GTP (Go Text Protocol).

(A decent chunk of this library was implemented or edited by Claude Code, with a lot of manual editing and work as well)

This library depends on sgfmill (`pip install sgfmill`) https://github.com/mattheww/sgfmill for sgf file handling, but doesn't depend on anything else.

## Main Files

* **gtpmatch.py** is the core library for launching bots and playing games and saving the sgf
* **sgf_utils.py** has a helper function for loading opening sequences to initialize games with

Also:

* **katago_roundrobin_example.py** - Example round-robin tournament script for KataGo bots. Edit and use this to easily play arbitrarily configured separate KataGo bots against each other when KataGo's built-in match command isn't suitable (e.g. you are testing settings that want the bots to run separately and not share caches, you want to test params like threads or batching that aren't variable, you want to use pondering and tunnel bot commands through ssh on separate machines...)

## TLDR

```python
import gtpmatch

# Launch two bots and play a game
with gtpmatch.launch_bot("Black", "gnugo --mode gtp --quiet") as black_bot, \
     gtpmatch.launch_bot("White", "gnugo --mode gtp --quiet") as white_bot:

    # Send any GTP commands to configure rules, time controls, etc
    black_bot.send_command("time_settings 0 1 1")
    white_bot.send_command("time_settings 0 1 1")

    # For handicap or custom starting positions, pass `handicap_or_startpos` into here.
    # See demo.py for more examples.
    game = gtpmatch.play_game(black_bot, white_bot, board_size=19, komi=6.5)

    print(f"Result: {game.result.value}")
    print(f"Winner: {game.winner()}")

    game.save_sgf("output.sgf")
```
