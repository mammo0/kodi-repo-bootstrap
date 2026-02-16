import re
from re import Match, Pattern
from typing import Any, Dict, Final, Optional


class SemanticVersion:
    __VERSION_REGEX: Final[Pattern] = re.compile(r"^(?P<major>0|[1-9]\d*)\.?"
                                                 r"(?P<minor>0|[1-9]\d*)?\.?"
                                                 r"(?P<patch>0|[1-9]\d*)?"
                                                 r"(?P<other>.*)$")

    def __init__(self, version_str: str) -> None:
        self.__major: int = 0
        self.__minor: Optional[int] = None
        self.__patch: Optional[int] = None
        self.__other: Optional[str] = None

        v_match: Optional[Match] = re.match(string=version_str, pattern=SemanticVersion.__VERSION_REGEX)
        if v_match is not None:
            v_match_dict: Dict[str, Any] = v_match.groupdict()

            self.__major = int(v_match_dict["major"])

            if v_match_dict["minor"] is not None:
                self.__minor = int(v_match_dict["minor"])

                # patch version makes only sense if there's a minor version
                if v_match_dict["patch"] is not None:
                    self.__patch = int(v_match_dict["patch"])

            # special case: match group "other" is always an empty string
            if v_match_dict["other"]:
                self.__other = v_match_dict["other"]

    @property
    def major(self) -> int:
        return self.__major

    @property
    def minor(self) -> Optional[int]:
        return self.__minor

    @property
    def patch(self) -> Optional[int]:
        return self.__patch

    @property
    def other(self) -> Optional[str]:
        return self.__other

    def __eq__(self, other_ver: object) -> bool:
        return str(self) == str(other_ver)

    def __gt__(self, other_ver: "SemanticVersion") -> bool:
        if self.__major != other_ver.major:
            return self.__major > other_ver.major

        if self.__minor is None and other_ver.minor is None:
            pass
        elif self.__minor is None and other_ver.minor is not None:
            return False
        elif self.__minor is not None and other_ver.minor is None:
            return True
        elif (
            self.__minor is not None and other_ver.minor is not None
            and self.__minor != other_ver.minor
        ):
            return self.__minor > other_ver.minor

        if self.__patch is None and other_ver.patch is None:
            pass
        elif self.__patch is None and other_ver.patch is not None:
            return False
        elif self.__patch is not None and other_ver.patch is None:
            return True
        elif (
            self.__patch is not None and other_ver.patch is not None
            and self.__patch != other_ver.patch
        ):
            return self.__patch > other_ver.patch

        if self.__other is None and other_ver.other is None:
            pass
        elif self.__other is None and other_ver.other is not None:
            return False
        elif self.__other is not None and other_ver.other is None:
            return True
        elif self.__other is not None and other_ver.other is not None:
            return sorted((self.__other, other_ver.other))[0] == self.__other

        return False

    def __ge__(self, other_ver: "SemanticVersion") -> bool:
        return self.__eq__(other_ver) or self.__gt__(other_ver)

    def __lt__(self, other_ver: "SemanticVersion") -> bool:
        return not self.__ge__(other_ver)

    def __le__(self, other_ver: "SemanticVersion") -> bool:
        return self.__eq__(other_ver) or self.__lt__(other_ver)

    def __str__(self) -> str:
        ver_str: str = f"{self.__major}"

        if self.__minor is not None:
            ver_str += f".{self.__minor}"

            if self.__patch is not None:
                ver_str += f".{self.__patch}"

        if self.__other is not None:
            ver_str += f"{self.__other}"

        return ver_str

    def __hash__(self) -> int:
        return hash(str(self))
