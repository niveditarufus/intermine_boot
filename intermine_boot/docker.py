from pathlib import Path
import pickle as pkl
import subprocess
import shutil
import os
from git import Repo,cmd
import yaml
from intermine_boot import utils


DOCKER_COMPOSE_REPO = 'https://github.com/intermine/docker-intermine-gradle'

ENV_VARS = ['env', 'UID='+str(os.geteuid()), 'GID='+str(os.getegid())]


def _is_conf_same(path_to_config, options):
    conf_file_path = str(path_to_config) + '/.config'
    if not os.path.isfile(conf_file_path):
        return False
    
    config = pkl.load(open(conf_file_path, 'rb'))
    try:
        if (config['branch_name'] == options['im_branch']) and (
                config['repo_name'] == options['im_repo']):
            return True
        else:
            return False
    except KeyError:
        return False


def _store_conf(path_to_config, options):
    config = {}
    config['branch_name'] = options['im_branch']
    config['repo_name'] = options['im_repo']

    f = open(path_to_config / '.config', 'wb')
    pkl.dump(config, f)
    return


def _get_compose_path(options, env):
    work_dir = env['data_dir'] / 'docker'
    compose_file = 'dockerhub.docker-compose.yml'
    if options['build_images']:
        compose_file = 'local.docker-compose.yml'
    return work_dir / compose_file

def _create_volume_dirs(compose_path):
    with open(compose_path, 'r') as stream:
        compose_dict = yaml.safe_load(stream)

        for service in compose_dict['services']:
            service_dict = compose_dict['services'][service]

            if 'volumes' not in service_dict:
                continue

            volumes = service_dict['volumes']

            for volume in volumes:
                volume_dir = volume.split(':')[0]
                Path(compose_path.parent / volume_dir).mkdir(parents=True, exist_ok=True)

def up(options, env):
    compose_path = _get_compose_path(options, env)

    same_conf_exist = False
    if compose_path.parent.is_dir():
        if _is_conf_same(env['data_dir'], options):
            print ('Same configuration exist. Running local compose file...') 
            same_conf_exist = True
        else:
            print ('Configuration change detected. Downloading compose file...')
            shutil.rmtree(compose_path.parent)
    
    if not same_conf_exist:
        Repo.clone_from(DOCKER_COMPOSE_REPO, compose_path.parent, 
                    progress=utils.GitProgressPrinter())

    _create_volume_dirs(compose_path)

    option_vars = (['IM_REPO_URL='+options['im_repo'],
                    'IM_REPO_BRANCH='+options['im_branch']]
                   if options['build_im'] else [])

    if not options['build_images']:
        # Make sure dockerhub images are up-to-date.
        subprocess.run(['docker-compose',
                        '-f', compose_path.name,
                        'pull'],
                       check=True,
                       cwd=compose_path.parent)


    subprocess.run([*ENV_VARS, *option_vars,
                    'docker-compose',
                    '-f', compose_path.name,
                    'up', '-d'] +
                   (['--build', '--force-recreate']
                    if options['build_images'] else []),
                   check=True,
                   cwd=compose_path.parent)
    
    _store_conf(env['data_dir'], options)


def down(options, env):
    compose_path = _get_compose_path(options, env)
    subprocess.run([*ENV_VARS,
                    'docker-compose',
                    '-f', compose_path.name,
                    'down'],
                   check=True,
                   cwd=compose_path.parent)


def monitor_builder(options, env):
    compose_path = _get_compose_path(options, env)
    # This command will print the logs from intermine_builder and exit
    # once it finishes building (blocking until then).
    subprocess.run(['docker-compose',
                    '-f', compose_path.name,
                    'logs', '-f', 'intermine_builder'],
                   check=True,
                   cwd=compose_path.parent)


def create_archives(options, env):
    compose_path = _get_compose_path(options, env)

    postgres_archive = env['data_dir'] / 'postgres'
    postgres_data_dir = compose_path.parent / 'data' / 'postgres'
    shutil.make_archive(postgres_archive, 'zip', root_dir=postgres_data_dir)

    solr_archive = env['data_dir'] / 'solr'
    solr_data_dir = compose_path.parent / 'data' / 'solr'
    shutil.make_archive(solr_archive, 'zip', root_dir=solr_data_dir)

    mine_archive = env['data_dir'] / 'biotestmine'
    mine_data_dir = compose_path.parent / 'data' / 'mine' / 'biotestmine'
    shutil.make_archive(mine_archive, 'zip', root_dir=mine_data_dir)
