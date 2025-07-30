import time
import random
import shlex

from pathlib import Path
from datetime import datetime, timezone, timedelta

import click
from dotenv import dotenv_values

CONFIG_PATH = Path.home() / ".brevesky"


@click.group()
def cli():
    pass


@cli.command()
def init():
    if CONFIG_PATH.exists():
        click.confirm(
            'La configuración de BreveSky ya existe. ¿Querés modificarla?',
            abort=True
        )

    handle = click.prompt(
        'Ingresá tu handle de Bluesky (ej: pepito.bsky.social)',
        type=str
    )
    password = click.prompt(
        'Ingresá tu contraseña',
        hide_input=True,
        type=str
    )
    timezone_ = click.prompt(
        'Ingresá tu diferencia horaria (ej: para Argentina es -3)',
        type=click.IntRange(min=-13, max=13),
        default=-3
    )

    content = (
        f'HANDLE={shlex.quote(handle)}\n'
        f'PASSWORD={shlex.quote(password)}\n'
        f'TIMEZONE={timezone_}\n'
    )

    CONFIG_PATH.write_text(content)


@cli.command()
@click.option('--from', 'from_', help='Fecha de inicio (YYYY-MM-DD)')
@click.option('--to', help='Fecha de fin (YYYY-MM-DD)')
def delete(from_, to):
    if CONFIG_PATH.exists() is False:
        raise click.ClickException(
            'No existe la configuración, ejecutá "brevesky init"'
        )

    if not from_ or not to:
        raise click.UsageError("Debés pasar ambos parámetros: --from y --to")

    cfg = dotenv_values(CONFIG_PATH)

    handle = cfg['HANDLE']
    password = cfg['PASSWORD']
    tz_diff = timezone(timedelta(hours=int(cfg.get('TIMEZONE', '0'))))

    start_at = datetime.strptime(from_, '%Y-%m-%d').replace(tzinfo=tz_diff)
    end_at = datetime.strptime(to, '%Y-%m-%d').replace(tzinfo=tz_diff)

    go_on = click.prompt(
        f'Vas a borrar el contenido de la cuenta {handle}\n'
        f'publicado entre las fechas {from_} y {to}\n'
        '¿Querés continuar? (y/N)',
        default='n',
        show_default=False
    ).strip().lower()

    if go_on not in ("y", "yes"):
        click.echo("Cancelado, no se borró nada")
        raise SystemExit(1)

    click.echo('Iniciando...')
    from atproto import Client  # lazy load

    click.echo('Conectado a Bluesky...')

    try:
        client = Client()
        client.login(handle, password)

    except Exception as e:
        click.secho(f"Error al iniciar sesión: {e}", fg="red")
        raise SystemExit(1)

    did = client.com.atproto.identity.resolve_handle(
        {'handle': handle}
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

        rows = len(response.feed)
        if rows == 0:
            break

        click.echo(f'Evaluando lote de {rows} publicaciones')

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

            click.echo(f'  Borrando {rkey}')

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

        rows = len(resp.records)
        if rows == 0:
            break

        click.echo(f'Evaluando lote de {rows} likes')

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

            click.echo(f'  Borrando {rkey}')

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
    cli()
