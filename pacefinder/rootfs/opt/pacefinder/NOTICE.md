# Notices

Pacefinder bundles small public datasets to keep the app useful out of the box.
Each is credited below; if a maintainer asks for the dataset to be removed or
attributed differently, file an issue.

## Forza Motorsport car ordinal database

`data/fm8_cars.csv` — base list of `ordinal → year/make/model` mappings used
by the car picker in the session-edit modal.

- **Source:** https://github.com/bluemanos/forza-motorsport-car-track-ordinal
- **Maintainer:** [@bluemanos](https://github.com/bluemanos)
- **Use here:** seed catalog so the picker isn't empty on first install.
  User-curated additions / overrides live in `data/fm8_cars_extended.csv`
  (loaded after the base; later entries win on duplicate ordinals).
