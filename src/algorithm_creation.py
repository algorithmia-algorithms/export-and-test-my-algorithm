
from src.images import *
from Algorithmia.errors import ApiError
from uuid import uuid4
from shutil import rmtree
import sh
import tarfile
import os

def initialize_algorithm(algoname, mode, destination_aems_master, destination_client):
    username = next(destination_client.dir("").list()).path
    algo = destination_client.algo(f"algo://{username}/{algoname}")
    try:
        _ = algo.info()
        print(f"algorithm {username}/{algoname} already exists; skipping initialization...")
        return algo
    except ApiError:
        print(f"algorithm {username}/{algoname} doesn't exist, creating...")

        return create_algorithm(algo, algoname, mode, destination_aems_master)


def create_algorithm(algo, algoname, mode, aems_master):
    if aems_master == "test":
        environment = TEST_IMAGES[mode]
    elif aems_master == "prod":
        environment = PROD_IMAGES[mode]
    else:
        raise Exception(f"aems master '{aems_master}' not part of available set")

    algo.create(
        details={
            "label": f"QA - {algoname} - {str(uuid4())}",
        },
        settings={
            "source_visibility": "closed",
            "license": "apl",
            "algorithm_environment": environment,
            "network_access": "full",
            "pipeline_enabled": True
        }
    )
    return algo


def migrate_datafiles(algo, data_file_paths, source_client, destination_client, working_directory):
    artifact_path = f"{working_directory}/source"
    os.makedirs(artifact_path, exist_ok=True)
    collection_path = f"data://{algo.username}/{algo.algoname}"
    if not destination_client.dir(collection_path).exists():
        destination_client.dir(collection_path).create()
        for path in data_file_paths:
            filename = path.split("/")[-1]
            deployed_file_path = f"{collection_path}/{filename}"
            local_datafile_path = source_client.file(path).getFile().name
            destination_client.file(deployed_file_path).putFile(local_datafile_path)
        print(f"data files uploaded for {collection_path}")
    else:
        print(f"{collection_path} already exists, assuming datafiles are correct; skipping migration...")


def update_algorithm(algo, remote_client, workspace_path, artifact_path):
    api_key = remote_client.apiKey
    api_address = remote_client.apiAddress
    destination_algorithm_name = algo.algoname
    destination_username = algo.username
    templatable_username = "<user>"
    repo_path = f"{workspace_path}/{destination_algorithm_name}"
    git_path = f"https://{algo.username}:{api_key}@git.{api_address.split('https://api.')[-1]}/git/{destination_username}/{destination_algorithm_name}.git"
    os.makedirs(artifact_path, exist_ok=True)
    os.makedirs(repo_path, exist_ok=True)
    sh.git.config("--global", "user.email", "ci@algorithmia.com")
    sh.git.config("--global", "user.name", "CI")
    clone_bake = sh.git.bake(C=workspace_path)
    publish_bake = sh.git.bake(C=repo_path)
    print(str(clone_bake.clone(git_path)))
    sh.rm("-r", f"{repo_path}/src")
    sh.cp("-R", f"{artifact_path}/src", f"{repo_path}/src")
    sh.cp("-R", f"{artifact_path}/requirements.txt", f"{repo_path}/requirements.txt")
    sh.xargs.sed(sh.find(repo_path, "-type", "f"), i=f"s/{templatable_username}/{destination_username}/g")
    try:
        publish_bake.add(".")
        publish_bake.commit(m="automatic initialization commit")
        print(str(publish_bake.status()))
        print(str(publish_bake.push()))
    except Exception as e:
        if "Your branch is up to date with" not in str(e):
            raise e
        else:
            print(
                f"algorithm {destination_username}/{destination_algorithm_name} is already up to date, skipping update...")
            rmtree(workspace_path)
            return algo
