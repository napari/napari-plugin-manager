# Changelog

## [v0.1.0](https://github.com/napari/napari-plugin-manager/tree/v0.1.0) (2024-07-24)

[Full Changelog](https://github.com/napari/napari-plugin-manager/compare/v0.1.0a2...v0.1.0)

**Implemented enhancements:**

- Add shortcut to close plugin manager dialog and quit application [\#64](https://github.com/napari/napari-plugin-manager/pull/64) ([goanpeca](https://github.com/goanpeca))
- Use the correct install tool or source depending on how napari was installed [\#47](https://github.com/napari/napari-plugin-manager/pull/47) ([goanpeca](https://github.com/goanpeca))
- Update lists without refreshing and other fixes [\#45](https://github.com/napari/napari-plugin-manager/pull/45) ([goanpeca](https://github.com/goanpeca))
- Do not destroy plugin dialog on close, just hide it [\#42](https://github.com/napari/napari-plugin-manager/pull/42) ([goanpeca](https://github.com/goanpeca))
- Add some small improvements to make the list load a bitfaster [\#41](https://github.com/napari/napari-plugin-manager/pull/41) ([goanpeca](https://github.com/goanpeca))
- Use display name on plugins that provide it [\#32](https://github.com/napari/napari-plugin-manager/pull/32) ([goanpeca](https://github.com/goanpeca))
- Reorganize list widget layout and fix issues [\#31](https://github.com/napari/napari-plugin-manager/pull/31) ([goanpeca](https://github.com/goanpeca))

**Fixed bugs:**

- Change base widget used to position install plugin pop up message/warning and delta [\#68](https://github.com/napari/napari-plugin-manager/pull/68) ([dalthviz](https://github.com/dalthviz))
- Fix constraint file creation and clean up logic on Windows [\#66](https://github.com/napari/napari-plugin-manager/pull/66) ([dalthviz](https://github.com/dalthviz))
- Pin numpy \<2 when installing plugins [\#19](https://github.com/napari/napari-plugin-manager/pull/19) ([Czaki](https://github.com/Czaki))

**Tasks:**

- Remove pydantic constraint [\#55](https://github.com/napari/napari-plugin-manager/pull/55) ([goanpeca](https://github.com/goanpeca))
- Add dependabot.yml [\#49](https://github.com/napari/napari-plugin-manager/pull/49) ([jaimergp](https://github.com/jaimergp))
- Update aganders/headless-gui@v2 \(silence nodejs warning on github actions\) [\#48](https://github.com/napari/napari-plugin-manager/pull/48) ([GenevieveBuckley](https://github.com/GenevieveBuckley))
- Move qss file from napari to plugin manager [\#43](https://github.com/napari/napari-plugin-manager/pull/43) ([goanpeca](https://github.com/goanpeca))
- Skip failing tests and use macos13 worker [\#40](https://github.com/napari/napari-plugin-manager/pull/40) ([goanpeca](https://github.com/goanpeca))
- Move npe2api.py from napari repo to this repo [\#39](https://github.com/napari/napari-plugin-manager/pull/39) ([goanpeca](https://github.com/goanpeca))
- Move conda util to utils module and clean up code [\#13](https://github.com/napari/napari-plugin-manager/pull/13) ([goanpeca](https://github.com/goanpeca))

**Documentation:**

- DOC Expand intro in readme [\#18](https://github.com/napari/napari-plugin-manager/pull/18) ([lucyleeow](https://github.com/lucyleeow))

## [v0.1.0a2](https://github.com/napari/napari-plugin-manager/tree/v0.1.0a2) (2023-06-13)

[Full Changelog](https://github.com/napari/napari-plugin-manager/compare/v0.1.0a1...v0.1.0a2)

**Fixed bugs:**

- Temporary remove napari from dependencies [\#9](https://github.com/napari/napari-plugin-manager/pull/9) ([Czaki](https://github.com/Czaki))

## [v0.1.0a1](https://github.com/napari/napari-plugin-manager/tree/v0.1.0a1) (2023-06-12)

[Full Changelog](https://github.com/napari/napari-plugin-manager/compare/v0.1.0a0...v0.1.0a1)

**Fixed bugs:**

- Add constraints for pydantic [\#6](https://github.com/napari/napari-plugin-manager/pull/6) ([jaimergp](https://github.com/jaimergp))

**Tasks:**

- Remove briefcase specific workarounds [\#8](https://github.com/napari/napari-plugin-manager/pull/8) ([jaimergp](https://github.com/jaimergp))
- safer publish way [\#5](https://github.com/napari/napari-plugin-manager/pull/5) ([Czaki](https://github.com/Czaki))



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*