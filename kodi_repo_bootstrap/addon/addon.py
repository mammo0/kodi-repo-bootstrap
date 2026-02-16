import re
import shutil
import zipfile
from importlib import resources
from io import BufferedReader, BufferedWriter, BytesIO, TextIOWrapper
from pathlib import Path
from typing import IO, TYPE_CHECKING, Final, List, Optional
from xml.dom import minidom
from xml.dom.minicompat import NodeList
from xml.dom.minidom import Document, Element, Node
from zipfile import ZipFile

from kodi_repo_bootstrap.fs.file import DEFAULT_FILE_ENCODING, File
from kodi_repo_bootstrap.repo.config import Config
from kodi_repo_bootstrap.repo.version import SemanticVersion

if TYPE_CHECKING:
    from xml.dom.minidom import _ElementChildren


class Addon:
    _ADDON_XML_FILE: Final[str] = "addon.xml"

    def __init__(self, addon_path: Path) -> None:
        self.__addon_root: Path = addon_path

        self.__addon_xml_bytes: Optional[bytes] = self.__get_file_bytes(Addon._ADDON_XML_FILE)
        if self.__addon_xml_bytes is None:
            raise ValueError(f"'{addon_path}' is not a regular addon directory or addon ZIP archive.")

        self.__parsed_xml: Document
        self.__xml_lines: List[str]
        with BytesIO(self.__addon_xml_bytes) as addon_xml_fp:
            self.__parsed_xml = minidom.parse(addon_xml_fp)

            # reset file descriptor
            addon_xml_fp.seek(0)

            self.__xml_lines = TextIOWrapper(addon_xml_fp).readlines()

        # the "addon" tag is the root tag
        root: NodeList[Element] = self.__parsed_xml.getElementsByTagName("addon")
        if len(root) != 1:
            raise ValueError(f"The addon.xml file of '{addon_path}' has the wrong format.")
        root_tag: Element = root[0]

        # id
        self.__id: str = root_tag.getAttribute("id")

        # version
        self.__version: SemanticVersion = SemanticVersion(root_tag.getAttribute("version"))

        # assets
        self.__asset_path_strs: List[str] = []

        extension: Element
        for extension in root_tag.getElementsByTagName("extension"):
            if extension.getAttribute("point") != "xbmc.addon.metadata":
                continue

            # find the 'assets' tag
            assets_tag: Element
            for assets_tag in extension.getElementsByTagName("assets"):
                # iterate over the assets
                asset: _ElementChildren
                for asset in assets_tag.childNodes:
                    # only process element nodes (<icon>, <fanart>, ...)
                    if asset.nodeType == Node.ELEMENT_NODE:
                        # the first child (Node.TEXT_NODE) of an asset element contains the path
                        child: Optional[_ElementChildren] = asset.firstChild
                        if child is not None and child.nodeType == Node.TEXT_NODE:
                            self.__asset_path_strs.append(child.nodeValue)

                # can exit here, because there is only one 'assets' tag
                break

            # the assets tag must be in the "xbmc.addon.metadata" extension
            break

    @property
    def addon_xml_lines(self) -> List[str]:
        return self.__xml_lines

    @property
    def id(self) -> str:
        return self.__id

    @property
    def version(self) -> SemanticVersion:
        return self.__version

    @property
    def addon_path(self) -> Path:
        return self.__addon_root

    def create_zip_file(self, dest_dir: Path, glob_pattern: str="**/*") -> None:
        # the path of the zip file
        zip_file_path: Path = dest_dir / f"{self.__id}-{self.__version}.zip"

        if self.__addon_root.is_file():
            print(f"'{self.__addon_root}' is already a ZIP archive. Just copy it.")

            shutil.copy2(src=self.__addon_root,
                         dst=zip_file_path)

        else:
            print(f"Generate zip file for addon: {self.__id}-{self.__version}")

            try:
                # create the zip file
                with ZipFile(zip_file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zip_content:
                    # iterate over the addon directory (default glob_pattern: "**/*")
                    current_path: Path
                    for current_path in self.__addon_root.glob(glob_pattern):
                        # ignore any dotfiles / dotdirectories
                        if any(part.startswith(".") for part in current_path.parts):
                            continue

                        # the directory structure in the ZIP file:
                        # <addon_id>-<addon_version>.zip
                        #              |- <addon_id>/
                        #              |      |- addon.xml
                        #              |      |- ...

                        # the root directory in the ZIP file is named with the addon ID
                        archive_path: Path = Path(self.__id)
                        # add all addon files relative to this ZIP root
                        archive_path = archive_path / current_path.relative_to(self.__addon_root)

                        zip_content.write(current_path, archive_path)
            except OSError:
                print(f"Error writing ZIP file: '{zip_file_path}'")

        # create md5 file for the zip file
        File.create_md5_file(zip_file_path)

    def copy_assets_to_dir(self, dest_dir: Path) -> None:
        print(f"Copying assets for addon: {self.__id}-{self.__version}")

        # copy addon.xml
        if self.__addon_xml_bytes is not None:
            addon_xml_copy: BufferedWriter
            with open(dest_dir / Addon._ADDON_XML_FILE, "wb") as addon_xml_copy:
                addon_xml_copy.write(self.__addon_xml_bytes)

        # copy the assets
        asset_path_str: str
        for asset_path_str in self.__asset_path_strs:
            asset_bytes: Optional[bytes] = self.__get_file_bytes(asset_path_str)

            if asset_bytes is not None:
                asset_copy: BufferedWriter
                with open(dest_dir / Path(asset_path_str).name, "wb") as asset_copy:
                    asset_copy.write(asset_bytes)

    def __get_file_bytes(self, file_path_str: str) -> Optional[bytes]:
        if self.__addon_root.is_file():
            zip_fp: ZipFile
            with ZipFile(self.__addon_root, 'r') as zip_fp:
                try:
                    # get the path of the compressed asset file
                    compressed_asset_path: str = [name
                                                    for name in zip_fp.namelist()
                                                    if re.match(rf"^[^/]+/{re.escape(file_path_str)}$", name)
                                                 ][0]

                    # read the asset file
                    compressed_asset_fp: IO[bytes]
                    with zip_fp.open(compressed_asset_path, 'r') as compressed_asset_fp:
                        return compressed_asset_fp.read()
                except IndexError:
                    print(f"Cannot find file '{file_path_str}' in ZIP file.")
        else:
            file_path = self.__addon_root / file_path_str
            if file_path.is_file():
                asset_fp: BufferedReader
                with open(file_path, "rb") as asset_fp:
                    return asset_fp.read()
            else:
                print(f"Cannot find file '{file_path_str}'.")

        return None


class RepoAddon(Addon):
    def __init__(self, config: Config) -> None:
        self.__config: Config = config

        # create repository addon path
        self.__repo_addon_dir: Path = config.repo_dir / config.repo_addon_id
        self.__repo_addon_dir.mkdir(exist_ok=True)

        # generate the addon.xml file for the repository addon
        self.__create_repo_addon_xml(addon_xml_path=self.__repo_addon_dir / Addon._ADDON_XML_FILE)

        super().__init__(addon_path=self.__repo_addon_dir)

    def __create_repo_addon_xml(self, addon_xml_path: Path) -> None:
        print("Create repository addon.xml")

        repo_addon_xml_template: Path
        with resources.path(package="kodi_repo_bootstrap", resource=".") as repo_addon_xml_template:
            repo_addon_xml_template = (repo_addon_xml_template / "res" / "repo_addon.xml.tpl").resolve()

        template_xml: str
        with open(repo_addon_xml_template, "r", encoding=DEFAULT_FILE_ENCODING) as f:
            template_xml = f.read()

        repo_xml: str = template_xml.format(
            addonauthor=self.__config.repo_addon_author,
            addondescription=self.__config.repo_addon_description,
            addonid=self.__config.repo_addon_id,
            addonsummary=self.__config.repo_addon_summary,
            addonversion=self.__config.repo_addon_version,
            reponame=self.__config.repo_name,
            repourl=self.__config.repo_url
        )

        # save file
        File.save_file(repo_xml, file_path=addon_xml_path)

    def create_zip_file(self, dest_dir: Optional[Path]=None, glob_pattern: str="") -> None:
        # add only the generated addon.xml file to
        super().create_zip_file(dest_dir=self.__repo_addon_dir, glob_pattern="addon.xml")
