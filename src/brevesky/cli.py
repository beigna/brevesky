import os
import time
import random

from pathlib import Path
from datetime import datetime, timezone, timedelta

from atproto import Client
from dotenv import load_dotenv
import click

env_path = Path.home() / ".brevesky"
load_dotenv(dotenv_path=env_path)

USERNAME = os.getenv('HANDLE')
PASSWORD = os.getenv('PASSWORD')
TZ_DIFF = int(os.getenv('TIMEZONE', '0'))
TZ = timezone(timedelta(hours=TZ_DIFF))


@click.command()
@click.option('--from', 'from_', required=True,
              help='Fecha de inicio (YYYY-MM-DD)')
@click.option('--to', required=True,
              help='Fecha de fin (YYYY-MM-DD)')
def main(from_, to):
    start_at = datetime.strptime(from_, '%Y-%m-%d').replace(tzinfo=TZ)
    end_at = datetime.strptime(to, '%Y-%m-%d').replace(tzinfo=TZ)

    go_on = click.prompt(
        f'Vas a borrar el contenido de la cuenta {USERNAME}\n'
        f'publicado entre las fechas {from_} y {to}\n'
        '¿Querés continuar? (y/N)',
        default='n',
        show_default=False
    ).strip().lower()

    if go_on not in ("y", "yes"):
        click.echo("Cancelado, no se borró nada")
        raise SystemExit(1)

    click.echo('Iniciando...')

    client = Client()
    client.login(USERNAME, PASSWORD)

    did = client.com.atproto.identity.resolve_handle(
        {'handle': USERNAME}
    )['did']

    cursor = None
    exists = True
    posts_count = 0
    reposts_count = 0
    likes_count = 0

    while exists:
        response = client.app.bsky.feed.get_author_feed({
            'actor': did,
            'limit': 100,
            'cursor': cursor,
        })

        click.echo(f'Evaluando lote de {len(response.feed)} publicaciones')

        for feed_post in response.feed:
            if not feed_post.post:
                continue

            post_time = datetime.fromisoformat(
                feed_post.post.indexed_at.replace('Z', '+00:00')
            )

            if post_time >= end_at:
                continue

            if post_time < start_at:
                exists = False
                break

            rkey = feed_post.post.uri.split('/')[-1]

            click.echo(f'Borrando {rkey}')

            if feed_post.reason:
                client.com.atproto.repo.delete_record({
                    'repo': did,
                    'collection': 'app.bsky.feed.repost',
                    'rkey': rkey,
                })
                reposts_count += 1

            else:
                client.com.atproto.repo.delete_record({
                    'repo': did,
                    'collection': 'app.bsky.feed.post',
                    'rkey': rkey,
                })
                posts_count += 1

            time.sleep(random.uniform(0, 1.5))

        click.echo(f'    Posts borrados {posts_count}')
        click.echo(f'    Reposts borrados {reposts_count}')

        if response.cursor:
            cursor = response.cursor

        else:
            break

    cursor = None
    exists = True

    while exists:
        resp = client.com.atproto.repo.list_records({
            'repo': did,
            'collection': 'app.bsky.feed.like',
            'limit': 100,
            'cursor': cursor,
        })

        click.echo(f'Evaluando lote de {len(resp.records)} likes')

        for like in resp.records:

            like_time = datetime.fromisoformat(
                like.value.created_at.replace('Z', '+00:00')
            )

            if like_time >= end_at:
                continue

            if like_time < start_at:
                exists = False
                break

            rkey = like.uri.split('/')[-1]

            client.com.atproto.repo.delete_record({
                'repo': did,
                'collection': 'app.bsky.feed.like',
                'rkey': rkey,
            })
            likes_count += 1

            time.sleep(random.uniform(0, 1.5))

        click.echo(f'    Likes borrados {likes_count}')

        if resp.cursor:
            cursor = resp.cursor

        else:
            break

    click.echo('Listo!')


if __name__ == '__main__':
    main()
