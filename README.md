# Meu Chapeu 🎩

Meu Chapeu is a minimalist Discord bot that streams audio from YouTube videos. It was built as a learning exercise and without using ready-made Discord-specific libraries. As such, it is not intended nor suitable for public hosting or large-scale use.

Users are responsible for ensuring their usage complies with applicable terms of service and copyright laws.

# Usage

- `/play <query>`: streams audio from a YouTube video. `<query>` can be either a YouTube video URL or a search query. If it's a search query, the bot will use the YouTube search and stream the top result.
- `/skip`: stops current stream and starts next one in queue, if it exists

To use commands, the user has to be connected to a voice channel the bot has access to.

# Building and running

This bot uses Docker. One way of getting it up and running is by using the [build_and_deploy.sh](https://github.com/rodrigo-weigert/meu-chapeu/blob/master/build_and_deploy.sh) script.

The script deploys the bot to a remote machine over SSH. To use it, files `.env` and `.deploy.env` must be created with the appropriate variables set. See [.env.example](https://github.com/rodrigo-weigert/meu-chapeu/blob/master/.env.example) and [deploy.env.example](https://github.com/rodrigo-weigert/meu-chapeu/blob/master/deploy.env.example) to learn how to create them.

To run without the script, just adapt the script's `docker build` and `docker run` commands to your needs. The `.env` variables are still required for the application to run.

## Discord scope and permission requirements

- `bot` [scope](https://docs.discord.com/developers/topics/oauth2#shared-resources)
- `CONNECT` and `SPEAK` [permissions](https://docs.discord.com/developers/topics/permissions) for the voice channels the bot will join
