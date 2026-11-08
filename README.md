# beanfx

Pixel-art effects drawn as code. Describe an effect, and the `/beanfx` skill draws it in Python and exports a
sprite sheet with JSON that any engine plays.

See the effects and the live demo at https://beanfx.vhbien000.workers.dev/

## Install

```
/plugin marketplace add baenv/beanfx
/plugin install beanfx@beanfx
```

Then run `/beanfx <description | image>` in any project. It needs Python 3.10+; the first run creates `.venv/`
(numpy, pillow) in that project and writes each effect to `drafts/<name>/`, with its own copy of the drawing kit
in `drafts/<name>/kit/`. Plugin updates leave the kit of an existing draft as it was.

## Credits

The light layer and the reuse path learn from [pixelfx](https://github.com/patch-gg/pixelfx) (MIT, Patch). beanfx
reimplements them in Python and ships no pixelfx code.

## License

MIT, see `LICENSE`.
