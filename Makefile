PREFIX := /usr

install: $(scripts)
	echo "IMPORTANT! We don't really install anything, we just create a symlink."
	ln -sf $(shell readlink -f ./synchrotron/sync-debian-package.py) $(DESTDIR)/usr/bin/sync-debian-package
	ln -sf $(shell readlink -f ./autorebuild/exec-autorebuild.sh) $(DESTDIR)/usr/bin/trigger-pkg-rebuild

clean:
	rm -f *.pyc

.PHONY: install clean
