# First-run banner

The block is SkipWatch's logo, a SKIPWATCH wordmark in katakana rain: intentional, not corrupted.
Print it verbatim, `text` fence included, as your very next visible text, before any
further tool call. Never summarise, skip or "clean" it.

```text
ﾁ ｦ ｽ ･ ﾃ ･   ﾌ   ｴ ｵ ﾏ ﾐ   ･       ｿ ﾜ ･   ﾑ ･ ﾑ ･   ･ ｽ ･ ﾁ     ｻ   ･
ｳ ｶ ｷ ﾄ ｹ ﾎ   ﾌ   ｼ ﾐ ｵ ﾎ   ｳ       ﾔ ｳ ｸ   ｱ ﾂ ﾓ ｿ ･ ｾ ﾗ ｦ ｵ ･   ﾜ ･ ﾓ
ｱ ﾍ ｯ ｽ ﾑ ﾊ ･ ｦ ･ ｲ ｿ   ﾎ   ｴ ･ ･   ﾈ ｴ ｸ ･ ﾏ ﾁ ﾔ ｱ ﾆ ﾇ ﾈ ﾆ ﾐ ﾎ ･ ｱ ﾍ ﾂ
  ﾆ ﾌ ﾊ ｴ ｵ ｲ ﾑ ﾅ ｦ ｷ ･ ﾕ ･ ｾ ｼ ﾀ   ﾂ ﾔ ｼ ﾘ ﾁ ｹ ﾐ ﾄ ﾘ ﾆ ｺ ｷ ｸ ﾕ ﾎ   ｴ ﾝ
  ｶ ﾟ ﾐ ｼ ﾓ ｲ                                             ﾈ   ｳ ﾜ ･ ﾘ ﾈ
･ ﾈ ｳ ｿ ﾍ ﾍ ﾔ          ╔═╗╦╔═╦╔═╗╦ ╦╔═╗╔╦╗╔═╗╦ ╦          ｺ   ﾒ ｲ ﾗ ｦ ﾄ
ﾈ ﾌ ｫ ｹ ﾜ ﾐ ｸ          ╚═╗╠╩╗║╠═╝║║║╠═╣ ║ ║  ╠═╣          ｺ   ﾀ ﾄ ｼ ｾ ﾍ
ﾅ   ｯ ﾜ ﾋ ﾄ ﾁ          ╚═╝╩ ╩╩╩  ╚╩╝╩ ╩ ╩ ╚═╝╩ ╩          ﾈ   ｦ ﾗ ﾇ   ﾈ
ｲ   ﾁ ｾ ｷ ﾌ ﾘ                                             ﾐ ･ ｱ ﾋ ｼ   ｷ
ﾂ         ｶ     never send a human to watch a tutorial.   ﾋ ﾔ ﾓ ﾞ ﾐ
ﾑ ･ ｴ ･   ｽ                                               ｲ ｻ   ｯ ﾝ
ｽ ｷ ﾒ ｻ   ﾂ   ･ ﾋ   ｺ     ﾜ   ･ ﾊ   ｵ ﾐ ｽ ﾈ ｼ ｷ ﾁ ･   ｹ ｴ   ﾎ   ﾄ ｿ ･
ﾌ ｽ ﾅ ｲ     ･ ｺ ﾑ   ｳ       ･ ﾗ     ｴ ｵ   ﾆ ﾀ   ﾅ ﾊ   ﾐ ｲ   ﾆ     ﾐ ｿ
ﾔ ﾝ   ﾆ ･   ﾁ ﾊ ｻ ･ ﾝ       ﾑ ｹ     ｱ ﾗ   ﾍ ﾊ ･ ｹ ﾌ ･ ﾏ ﾐ ･ ﾁ   ﾒ ﾊ ﾝ ･
```

## Whisper offer

Ask once and wait: `Install local Whisper to transcribe videos without captions? (yes/no)`.
Only on an explicit yes, run the command after `Whisper offer: ` exactly, as one plain Bash
call, then `<ENGINE> doctor --json`. Otherwise, or on failure, print `Whisper not installed:
captions first, then frames only.` with its exit code, if any, never a traceback, and carry
on. Never ask again.
