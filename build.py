import json
import os
from shutil import copy, make_archive

from totcommon.builder import builder
from src._constants import VERSION, NAME, ORGNAME, URL


def validate_sidecar(definition):
    """Check the stamped sidecar against VGCT's schema before it ships.

    A malformed sidecar is invisible here -- the exe builds, the zip is
    fine -- and only surfaces when someone loads the tool into a graph and
    it refuses. The schema lives in ``extensions/vgct.schema.json``,
    a copy of the published one; if it drifts, replace that file.

    Raises rather than warning: a package that cannot be loaded is not a
    package worth publishing.
    """
    schema_path = os.path.join("extensions", "vgct.schema.json")
    if not os.path.isfile(schema_path):
        print("warning: no schema at " + schema_path +
              ", sidecar NOT validated")
        return

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("warning: jsonschema is not installed, sidecar NOT validated "
              "(pip install -r requirements.txt)")
        return

    with open(schema_path, encoding="utf-8") as f:
        validator = Draft202012Validator(json.load(f))

    errors = sorted(validator.iter_errors(definition),
                    key=lambda e: list(e.absolute_path))
    if errors:
        for error in errors:
            where = "/".join(str(part) for part in error.absolute_path)
            print("sidecar invalid at {}: {}".format(where or "(root)",
                                                     error.message))
        raise SystemExit("sidecar does not satisfy VGCT's schema")

    print("sidecar validates against VGCT's schema")


def write_sidecar(exe_name, version):
    """Ship the VGCT sidecar next to the built binary and re-zip.

    The definition is authored by hand in
    ``extensions/<name>.vgct.json``; edit that file to change AutoPak's
    inputs/outputs/arguments. Here we only stamp the build-derived fields
    (version/name/id/executable) so they can never drift from the actual
    binary, then write the result beside the exe.
    """
    filename = exe_name + ".vgct.json"
    source = os.path.join("extensions", filename)
    if not os.path.isfile(source):
        print("warning: sidecar source not found, skipping: " + source)
        return

    with open(source) as f:
        definition = json.load(f)

    definition["version"] = version
    definition["name"] = exe_name
    definition["id"] = exe_name.lower()
    definition["executable"] = {"value": exe_name + ".exe"}

    validate_sidecar(definition)

    dist_dir = "./dist/" + exe_name + "-v" + str(version)
    exe_dir = dist_dir + "/" + exe_name
    with open(os.path.join(exe_dir, filename), "w") as f:
        json.dump(definition, f, indent=2)

    make_archive(dist_dir, "zip", dist_dir)


builder(NAME, ORGNAME, URL, VERSION)
write_sidecar(NAME, VERSION)
