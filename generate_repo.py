"""
    Repository, addons.xml and addons.xml.md5 structural generator

        Modifications:

        - by Rodrigo@TVADDONS: Zip plugins/repositories to a "zip" folder
        - BartOtten: Create a repository addon, skip folders without addon.xml, user config file
        - Twilight0@TVADDONS: Ignore .idea subdirectories in addons' directories, changed from md5 module to hashlib
                              copy changelogs, icons and fanarts

    This file is provided "as is", without any warranty whatsoever. Use at your own risk
"""

from argparse import ArgumentParser
import glob
import hashlib
from io import TextIOWrapper, IOBase
import itertools
import json
import os
import re
import shutil
import sys
from urllib.parse import urlparse
from xml.dom import minidom
from xml.dom.minidom import Node
import zipfile


# global variables
__PROGRAM_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__))))
CONFIG_FILE = os.path.join(__PROGRAM_DIR, 'config.json')
TEMPLATE_FILE = os.path.join(__PROGRAM_DIR, 'repo_addon.xml.tpl')


class Generator:
    """
        Generates a new addons.xml file from each addons addon.xml file
        and a new addons.xml.md5 hash file. Only handles single depth folder structure.
    """

    def __init__(self, config):
        self.config = config

        # create the output path
        if not os.path.exists(self.config.out_dir):
            os.makedirs(self.config.out_dir)

        # create repository addon path
        self.repo_addon_path = os.path.join(self.config.out_dir, self.config.addon_id)
        if not os.path.exists(self.repo_addon_path):
            os.makedirs(self.repo_addon_path)

    def write_repo_addon_xml(self):
        print("Create repository addon.xml")

        with open(TEMPLATE_FILE, "r") as f:
            template_xml = f.read()

        repo_xml = template_xml.format(
            addonauthor=self.config.addon_author,
            addondescription=self.config.addon_description,
            addonid=self.config.addon_id,
            addonsummary=self.config.addon_summary,
            addonversion=self.config.addon_version,
            reponame=self.config.repo_name,
            repourl=self.config.repo_url)

        # save file
        self.__save_file(repo_xml, file_path=os.path.join(self.repo_addon_path, "addon.xml"))

    def generate_addon_zip_files(self):
        # loop thrugh all addon directories and add each addons addon.xml file
        for addon_direcotry in self.config.get_addon_directories():
            addon_xml_path = os.path.join(addon_direcotry, "addon.xml")
            try:
                # extract version and addon ID from the addon.xml
                version, addonid = self.__get_addon_xml_tag(addon_xml_path, "version", "id")

                # zip the addon
                self.__generate_zip_file(addon_direcotry, version, addonid)
            except Exception as e:
                print(e)

        # special case repository addon: only add addon.xml to zip file
        self.__generate_zip_file(self.repo_addon_path, self.config.addon_version, self.config.addon_id,
                                 only_addonxml=True)

    def __generate_zip_file(self, addon_directory, version, addon_id, only_addonxml=False):
        # create output addon directory
        addon_out_path = os.path.join(self.config.out_dir, addon_id)
        if not os.path.exists(addon_out_path):
            os.makedirs(addon_out_path)

        # the path of the zip file
        zip_file_path = os.path.join(addon_out_path, addon_id + "-" + version + ".zip")

        # skip if the zip file is already present
        if os.path.isfile(zip_file_path):
            print("Skipped creating " + os.path.basename(zip_file_path) + " file, because it exists already")
            return
        else:
            print("Generate zip file for " + addon_id + " " + version)

        try:
            # create the zip file
            zip_content = zipfile.ZipFile(zip_file_path, 'w', compression=zipfile.ZIP_DEFLATED)
            # fill it
            for current_root, dirs, files in os.walk(addon_directory):
                # ignore .svn and .git directories
                if '.svn' in dirs:
                    dirs.remove('.svn')
                if '.git' in dirs:
                    dirs.remove('.git')

                # write the current root folder
                rel_path = os.path.join(addon_id, os.path.relpath(current_root, addon_directory))
                zip_content.write(current_root, rel_path)

                # write the files in the current root folder
                for file in files:
                    # ignore dotfiles
                    if not file.startswith('.') and \
                            file != os.path.basename(zip_file_path):
                        # skip any other file if only the addon.xml file should be added
                        if only_addonxml and os.path.basename(file) != "addon.xml":
                            continue

                        rel_path = os.path.join(addon_id,
                                                os.path.relpath(os.path.join(current_root, file), addon_directory))
                        zip_content.write(os.path.join(current_root, file), rel_path)

                # since the addon.xml file is in the root directory we don't need to add any sub-directories
                if only_addonxml:
                    break

            zip_content.close()
        except Exception as e:
            print(e)
        else:
            # create md5 file for the zip file
            self.__create_md5_file(zip_file_path)

    def generate_repo_addons_file(self):
        print("Generating addons.xml file")

        # addons.xml opening tags
        addons_xml_data = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n'

        # store the content of all addon.xml files
        addon_xml_files = {}

        # get the addon.xml from previous addon versions
        # these versions are present in the already zipped addons
        for existing_zip_file in glob.iglob(os.path.join(self.config.out_dir, "*", "*.zip")):
            try:
                with zipfile.ZipFile(existing_zip_file, 'r') as zip_fp:
                    # get the path of the compressed addon.xml file
                    compressed_addon_xml_path = [name
                                                 for name in zip_fp.namelist()
                                                 if re.match(r"^[^/]+/addon\.xml$", name)][0]

                    # read the addon.xml
                    with zip_fp.open(compressed_addon_xml_path, 'r') as compressed_addon_xml_fp:
                        # save the content of the existing addon.xml based on the addon ID and version
                        addon_xml_content = TextIOWrapper(compressed_addon_xml_fp)
                        addonid, version = self.__get_addon_xml_tag(addon_xml_content, "id", "version")

                        if addonid in addon_xml_files:
                            addon_xml_files[addonid][version] = addon_xml_content.read().splitlines()
                        else:
                            addon_xml_files[addonid] = {version: addon_xml_content.read().splitlines()}
            except Exception as e:
                pass

        # loop through the addon directories and add each addons addon.xml file
        for addon_directory in itertools.chain(self.config.get_addon_directories(), [self.repo_addon_path]):
            try:
                addon_xml_path = os.path.join(addon_directory, "addon.xml")

                with open(addon_xml_path, "r") as addon_xml_fp:
                    addonid, version = self.__get_addon_xml_tag(addon_xml_fp, "id", "version")

                    if addonid in addon_xml_files:
                        addon_xml_files[addonid][version] = addon_xml_fp.read().splitlines()
                    else:
                        addon_xml_files[addonid] = {version: addon_xml_fp.read().splitlines()}
            except Exception as e:
                # poorly formatted addon.xml
                print("Excluding %s; error in addon.xml (%s)" % (addon_xml_path, e))

        # iterate over all found addon.xml files
        for addon_versions in addon_xml_files.values():
            for addon_xml_lines in addon_versions.values():
                # new addon
                addon_xml_data = ""
                # loop thru cleaning each line
                for line in addon_xml_lines:
                    # skip encoding format line
                    if (line.find("<?xml") >= 0):
                        continue
                    # add line
                    addon_xml_data += line.rstrip() + "\n"
                # we succeeded so add to our final addons.xml text
                addons_xml_data += addon_xml_data.rstrip() + "\n\n"

        # clean and add closing tag
        addons_xml_data = addons_xml_data.strip() + "\n</addons>\n"

        addons_xml_path = os.path.join(self.config.out_dir, "addons.xml")
        # save file
        self.__save_file(addons_xml_data, file_path=addons_xml_path)
        # create addons.xml.md5
        self.__create_md5_file(addons_xml_path)

    def __create_md5_file(self, file_path):
        print(f"Generating {os.path.basename(file_path)}.md5 file")

        hash_md5 = hashlib.md5()

        try:
            # create a new md5 hash
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)

            # save file
            self.__save_file(hash_md5.hexdigest(), file_path=file_path + ".md5")
        except Exception as e:
            # oops
            print(f"An error occurred creating {os.path.basename(file_path)}.md5 file!\n{e}")

    def __save_file(self, data, file_path):
        try:
            # write data to the file
            open(file_path, "w").write(data)
        except Exception as e:
            # oops
            print("An error occurred saving %s file!\n%s" % (file_path, e))

    def __get_addon_xml_tag(self, addon_xml_file_or_fp, *tags):
        # extract version and addon ID from the addon.xml
        parsed_xml = minidom.parse(addon_xml_file_or_fp)

        # reset file descriptor if it is one
        if isinstance(addon_xml_file_or_fp, IOBase):
            addon_xml_file_or_fp.seek(0)

        # the 'addon' tag is the parent
        for parent in parsed_xml.getElementsByTagName("addon"):
            if len(tags) == 1:
                # only return the single attribute
                return parent.getAttribute(tags[0])
            elif len(tags) > 1:
                # return multiple tags
                result = []
                for tag in tags:
                    result.append(parent.getAttribute(tag))
                return result


class AssetCopier:
    def __init__(self, config):
        self.config = config

    def copy_assets(self):
        # iterate over the addon directories
        for addon_directory in self.config.get_addon_directories():
            addon_xml_path = os.path.join(addon_directory, "addon.xml")
            addon_xml = minidom.parse(addon_xml_path)

            for parent in addon_xml.getElementsByTagName("addon"):
                addon_id = parent.getAttribute("id")
                addon_out_path = os.path.join(self.config.out_dir, addon_id)
                # a trailing slash is required by shutil.copy2 to preserve the file name at the destination
                addon_out_path = os.path.join(addon_out_path, '')

                # copy addon.xml
                shutil.copy2(addon_xml_path, addon_out_path)

                for extension in parent.getElementsByTagName("extension"):
                    if extension.getAttribute("point") != "xbmc.addon.metadata":
                        continue

                    # find the 'assets' tag
                    for assets in extension.getElementsByTagName("assets"):
                        # iterate over the assets
                        for asset in assets.childNodes:
                            # only process element nodes (<icon>, <fanart>, ...)
                            if asset.nodeType == Node.ELEMENT_NODE:
                                # the first child (Node.TEXT_NODE) of an asset element contains the path
                                asset_path_rel = asset.firstChild.nodeValue
                                asset_path_src = os.path.join(addon_directory, asset_path_rel)
                                asset_path_dest = os.path.join(addon_out_path, asset_path_rel)

                                # create the destination path if it doesn't exist
                                if not os.path.exists(os.path.dirname(asset_path_dest)):
                                    os.makedirs(os.path.dirname(asset_path_dest))

                                # copy the asset (if it exists)
                                if os.path.isfile(asset_path_src):
                                    shutil.copy2(asset_path_src, asset_path_dest)

                        # can exit here, because there is only one 'assets' tag
                        break


class Config:
    def __init__(self):
        # create the cli argument parser
        parser = self.__init_parser()

        # get the settings from the config file
        config = self.__read_config_file(CONFIG_FILE)

        # merge config file and cli arguments
        args = parser.parse_args()
        argparse_dict = vars(args)
        config.update({k: v for k, v in argparse_dict.items() if v})

        # check the config parameter
        self.__validate_config(config)

        # add the config attributes to this instance
        for key, value in config.items():
            setattr(self, key, value)

        # save the config to file
        self.__write_config_file(config, CONFIG_FILE)

    def __init_parser(self):
        parser = ArgumentParser(description="Create a Kodi repository")
        parser.add_argument('-n', '--name', metavar='Repository name', type=str, dest='repo_name',
                            help="The name of the repository")
        parser.add_argument('-r', '--id', metavar='Repository addon ID', type=str, dest='addon_id',
                            help="The ID of the repository addon (must start with 'repository.')")
        parser.add_argument('-v', '--version', metavar='Version', type=str, dest='addon_version',
                            help="The version of the repository addon")
        parser.add_argument('-a', '--author', metavar='Author', type=str, dest='addon_author',
                            help="The author of the repository")
        parser.add_argument('-s', '--summary', metavar='Summary', type=str, dest='addon_summary',
                            help="A short summary of this repository")
        parser.add_argument('-d', '--description', metavar='Description', type=str, dest='addon_description',
                            help=("The description can be longer. Using [CR] you can create a newline. ",
                                  "The use of other markup is not advised."))
        parser.add_argument('-u', '--url', metavar='Remote repository URL', type=str, dest='repo_url',
                            help=("The later URL of the repository main directory, e.g. ",
                                  "https://raw.githubusercontent.com/Your-Github-Username/repository-link/"))
        parser.add_argument('-i', '--input-dir', metavar='Input directory', type=str, dest='in_dir',
                            help="The directory containing the addons that should be added to the repository")
        parser.add_argument('-o', '--output-dir', metavar='Output directory', type=str, dest='out_dir',
                            help="The output directory of the repository")

        return parser

    def __validate_config(self, config):
        # check for missing and wrong settings
        missing_args = []
        wrong_args = []
        if not config['repo_name']:
            missing_args.append("--name")
        if not config['addon_id']:
            missing_args.append("--id")
        elif not config['addon_id'].startswith('repository.'):
            wrong_args.append("--id: The addon ID must start with 'repository.'")
        if not config['addon_version']:
            missing_args.append("--version")
        if not config['addon_author']:
            missing_args.append("--author")
        if not config['addon_summary']:
            missing_args.append("--summary")
        if not config['addon_description']:
            missing_args.append("--description")
        if not config['repo_url']:
            missing_args.append("--url")
        else:
            # remove trailing slash if it's there
            if config['repo_url'].endswith('/'):
                config['repo_url'] = config['repo_url'][:-1]

            # check for a valid URL
            parsed_url = urlparse(config['repo_url'])
            if not parsed_url.scheme or \
                    not parsed_url.netloc:
                wrong_args.append("--url: a valid URL must be provided")
        if not config['in_dir']:
            missing_args.append("--input-dir")
        else:
            if not os.path.isdir(config['in_dir']):
                wrong_args.append("--input-dir: a valid directory must be provided")
        if not config['out_dir']:
            missing_args.append("--output-dir")
        # if the output directory does not exist, it will be created later

        if missing_args:
            print('the following arguments are required:\n\t%s' % '\n\t'.join(missing_args),
                  file=sys.stderr)
            sys.exit(1)
        if wrong_args:
            print('there were errors with the following arguments:\n\t%s' % '\n\t'.join(wrong_args),
                  file=sys.stderr)
            sys.exit(1)

    def __read_config_file(self, file_path):
        # check if a config file exists
        if not os.path.isfile(file_path):
            # create a new one if no config file exists
            with open(file_path, 'w') as f:
                json.dump({}, f)

        # load the config file
        with open(file_path, 'r') as f:
            try:
                config = json.load(f)
            except Exception:
                config = {}

        # return the content of the config file as dict
        return config

    def __write_config_file(self, config, file_path):
        # write the config to file
        with open(file_path, 'w') as f:
            json.dump(config, f, sort_keys=True, indent=4)

    def get_addon_directories(self):
        for f in os.listdir(self.in_dir):
            full_path = os.path.join(self.in_dir, f)

            # only directories are valid
            if not os.path.isdir(full_path):
                continue

            # an addon.xml file must exist
            if not os.path.isfile(os.path.join(full_path, "addon.xml")):
                continue

            yield full_path


if __name__ == "__main__":
    # load the config
    config = Config()

    # generate files
    g = Generator(config)
    g.write_repo_addon_xml()
    g.generate_repo_addons_file()
    g.generate_addon_zip_files()

    # copy assets
    ac = AssetCopier(config)
    ac.copy_assets()

    print("Finished updating addons xml & md5 files, zipping addons and copying additional files")
