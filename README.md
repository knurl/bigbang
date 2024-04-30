# bigbang

## Important

**NB: Before you run bigbang.py:** Make sure you do the following:

- update `my-vars.yaml`, to specify your new setup
- write a new license file into `license.secret`

## How to install it

### Homebrew

Run setup.sh in the main directory:

```
./setup.sh
```

__NB__: Some of these packages, including google-cloud-sdk, will require you to
add things to your .zshrc, .bashrc, .zprofile, .profile or other dotfiles in
order to ensure that the right binaries are in your PATH, and to ensure that
you have tab-completion on the binaries. _Make sure that you pay attention to
the messages that come from the installations_.

## Other

Bigbang makes heavy use of Unicode characters for representing useful visual
elements such as arrows and progress meters. Users are strongly advised to use
a monospace font with a full representation of Plane 0, which includes the
arrows (U+2500–U+257F) and box-drawing characters (U+2500–U+257F). I highly
recommend [Iosevka](https://en.wikipedia.org/wiki/Iosevka), which renders
beautifully.

====
