# AutoPak

Finds every custom asset a compiled Source Engine map depends on, and writes the file
list `bspzip -addlist` consumes.

Download: [see the release page](https://github.com/The-Orange-Toolbox/AutoPak/releases)

A map's custom content — materials, models, sounds, particles, scripts — lives as loose
files in your mod folder. Unless those files are embedded into the BSP, everyone who
loads your map sees purple checkerboards and missing-model ERRORs. Finding the
dependencies by hand is impractical: a material pulls in textures, a model pulls in
materials which pull in textures, a particle system pulls in both, and entity keyvalues
scatter references across dozens of undocumented keys.

AutoPak walks that graph for you and tells you exactly what it found — and, more
usefully, what it could not find.

## The idea

AutoPak deliberately stops at the list. It does not run `bspzip`, does not need to find
`bspzip.exe`, and never modifies your map. You run `bspzip` yourself, and you are free to
open the list and append your own entries first.

That split is what makes the tool safe to drop into a compile chain: a bad run costs you
a text file, not a map.

It also decides what to pack differently from other packers:

| Where the asset is | What AutoPak does |
|---|---|
| A loose file in your content folders | **Packs it.** |
| Only inside a VPK | **Skips it** — that is the base game's, and every player already has it. |
| Loose *and* in a VPK | Packs it, and warns. Usually deliberate; occasionally a decompiled stock asset bloating your download. |
| Nowhere at all | **Reports it.** This is the part you actually want. |

VPKs are only ever opened to answer "does this exist?". Their contents are never
extracted and never packed.

## Usage

Run `AutoPak --help` for the full list.

```
AutoPak <map.bsp> [options]
```

| Argument | Meaning |
|---|---|
| `map.bsp` | The compiled map to scan. Never modified. |
| `-g`, `--game DIR` | Mod folder holding `gameinfo.txt`. Default: walk up from the BSP. |
| `-s`, `--source-directory DIR` | An extra loose content root. Repeatable. |
| `--profile NAME` | The BSP profile to read with (`TF2`, `P2`, `L4D2`…). Default: autodetect. |
| `--no-vpk` | Do not read the VPKs. Anything not loose is then reported missing. |
| `-i`, `--include PATH` | Force-pack a file nothing references. Repeatable. |
| `--include-dir DIR` | Force-pack a directory, recursively. Repeatable. |
| `--include-file-list FILE` | Force-pack the entries in a list. Same format AutoPak writes. |
| `-e`, `--exclude PATH` | Never pack this file. Repeatable. |
| `--exclude-dir DIR` | Never pack anything under this directory. Repeatable. |
| `--exclude-vpk VPK` | Never pack anything this VPK already contains. Repeatable. |
| `--no-swvtx` | Skip the `.sw.vtx` software-rendering meshes. |
| `--rename-nav` | List the nav mesh as `maps/embed.nav`. |
| `--rename-particle-manifest` | List the particle manifest as `particles.txt`. |
| `--no-utility-files` | Skip the pass that probes for nav, soundscapes, overviews, and language files. |
| `-o`, `--output FILE` | Where to write the list. Default: `<map>_files.txt` beside the BSP. |
| `--stdout` | Write the list to stdout instead of a file. |
| `--report {summary,detailed,json}` | How much to print. Default `summary`. |
| `--strict` | Exit with an error if anything is missing. |
| `-v`, `--verbose` | Print every asset as it resolves. |
| `-q`, `--quiet` | Print only the missing-file report and errors. |

Then pack, with the game's own `bspzip`:

```
AutoPak "…\tf\maps\mymap.bsp"
bspzip -addlist "…\tf\maps\mymap.bsp" mymap_files.txt "…\tf\maps\mymap.bsp"
```

`bspzip` needs `VPROJECT` set to your mod folder.

### Using with Hammer (expert compile)

- Copy `AutoPak.exe` into your `bin` folder (e.g. `steamapps/common/Team Fortress 2/bin`).
- In Hammer's expert compile window, use "New" to add a command.
- For the command, click "Cmds", select "executable", and pick `AutoPak.exe`.
- For the parameters, use `$bsp$ --game $gamedir$`.
- Add a second command for `bspzip` with `-addlist $bsp$ $path$$file$_files.txt $bsp$`.
- Order both after the copy command.

### Using with command line

`AutoPak --help` gives complete information about its usage.

## Output

```
The Orange Toolbox - AutoPak.exe (Aug 30 2026)

reading cp_vanguard.bsp
search paths:       6 directories, 4 vpks
crawling:           0...1...2...3...4...5...6...7...8...9...10 (1.2)
3 missing file(s):
  materials/custom/broken.vmt      (func_brush "material")
  models/props/missing.mdl         (prop_static)
  sound/custom/gone.wav            (ambient_generic "message")
1 warning(s):
  loose file shadows VPK content: materials/concrete/concretefloor001a.vmt
packed 412 files: 180 materials, 96 textures, 61 models, 48 sounds, 27 other.
skipped 1043 stock, 22 already in bsp, 44 soundscript references.
wrote cp_vanguard_files.txt
0.4 seconds elapsed
```

The missing-file report prints even under `-q`. It is the main reason to run the tool.

## What it finds

Seeded from the map itself: brush materials, the skybox, detail materials and sprites,
static and detail prop models, and anything already in the map's own pakfile. Then from
the entities: material, model, sound and particle keyvalues, plus the entity I/O commands
that name assets at runtime (`SetModel`, `PlayVO`, `r_screenoverlay`, `RunScriptFile`,
and the VScript equivalents).

From there it follows the dependencies: models to their `.vvd`/`.vtx`/`.phy` siblings,
their materials, their `$includemodel`s and their gibs; materials to their textures and
through `Patch { include }` chains; particles to their materials and models; VScripts to
the scripts, models and sounds they precache; `.res` files to their images; soundscapes
and soundscripts to their `wave` entries.

## Packing hints in VScript

A `.nut` can name content AutoPak has no way to infer:

```squirrel
// !CompilePal::IncludeFile("materials/custom/thing.vmt")
// !CompilePal::IncludeDirectory("materials/custom/set")
```

The `!CompilePal::` spelling is the portable one and is what you should write.
`!AutoPak::` is accepted as an alias.

## Known non-goals

**Soundscript entry names are not resolved.** Keys like `message` and `startsound`
usually hold a soundscript entry (`Ambient.Wind`) rather than a file path. AutoPak
recognises these and counts them separately rather than reporting them as missing, but it
does not read `game_sounds` manifests to find the `.wav` files behind them. Pack those
with `--include` if you need them.

**CS:GO and CS2 are out of scope.**

**Compressed (LZMA) BSPs are not supported.** Decompress first with `bspzip -repack`.

<!--- start txt omit -->
## Building from source

```bat
build.bat
```

Produces `dist/AutoPak-v<version>/` with a standalone one-file exe, the VGCT
sidecar, and the CompilePal plugin configuration, plus a zip of the lot.

## Running from source

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python src\__main__.py "…\tf\maps\mymap.bsp"
```

Tests:

```bat
.venv\Scripts\python -m unittest discover -s tests
```

Everything but the end-to-end check runs with no game installed.

## Project layout

```
src/__main__.py       CLI
src/pack.py           the run, start to finish
src/gameinfo.py       find the game, read its search paths
src/content.py        loose / VPK / missing resolution
src/vpk.py            minimal VPK directory reader, names only
src/bspseeds.py       BSP lumps -> the initial references
src/entities.py       entity keyvalues -> references
src/entityio.py       entity I/O -> references
src/utilityfiles.py   the sidecar files a map conventionally has
src/graph.py          the dependency walk
src/filelist.py       the bspzip list
src/keys.py           the asset keyword tables
src/paths.py          path normalisation
src/formats/          one minimal parser per file format
tests/                the above, plus the CLI and the sidecar
extensions/           VGCT tool definition, and the schema it is
                      checked against at build time and in the tests
plugins/compilepal/   CompilePal plugin configuration
```
<!--- end txt omit -->

## Prior art

The dependency rules are ported from [CompilePal](https://github.com/ruarai/CompilePal)'s
PACK step, which worked them out the hard way over many years. AutoPak is the standalone
command-line equivalent, built on the
[pySourceSDK](https://github.com/pySourceSDK) libraries.

## License

GPL-3.0. Built on [`valvebsp`](https://pypi.org/project/valvebsp/),
[`valvemdl`](https://pypi.org/project/valvemdl/) and
[`valvepcf`](https://pypi.org/project/valvepcf/).
