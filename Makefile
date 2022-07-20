ENVNAME := snap

.ONESHELL:
ENV_PREFIX=$(conda info | grep -i ${ENVNAME} | awk '{print $5}')
USING_POETRY=$(shell grep "tool.poetry" pyproject.toml && echo "yes")

help:             ## Show the help.
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@fgrep "##" Makefile | fgrep -v fgrep

show:             ## Show the current environment.
	@echo "Current environment:"
	@if [ "$(USING_POETRY)" ]; then poetry env info && exit; fi
	@echo "Running using $(ENV_PREFIX)"
	@$(ENV_PREFIX)python -V
	@$(ENV_PREFIX)python -m site

release:          ## Create a new tag for release.
	@echo "WARNING: This operation will create a version tag and push to github"
	@read -p "Version? (provide the next x.y.z semver) : " TAG
	@echo "$${TAG}" > snapshot/VERSION
	@$(ENV_PREFIX)gitchangelog > HISTORY.md
	@git add snapshot/VERSION HISTORY.md
	@git commit -m "release: version $${TAG}"
	@echo "creating git tag : $${TAG}"
	@git tag $${TAG}
	@git push -u origin HEAD --tags
	@echo "Github Actions will detect the new tag and release the new version."