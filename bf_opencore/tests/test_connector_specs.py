
"""Verify valid CONNECTOR_SPEC objects are present in each connector."""

from collections import OrderedDict
import pytest
import bf_opencore.connectors


MODULES = [getattr(connectors, c.name) for c in connectors.CONNECTORS]


@pytest.mark.parametrize('module', MODULES)
def test_specs_present(module):
    """Verify CONNECTOR_SPEC object is present in each connector.

    We'll try to look up the CONNECTOR_SPEC object in each.  This will
    raise an exception if the CONNECTOR_SPEC does not exist, or isn't
    imported in __init__.py
    """
    assert hasattr(module, 'CONNECTOR_SPEC'), \
        '{}.CONNECTOR_SPEC does not exist'.format(module.__name__)


@pytest.mark.parametrize('module', MODULES)
def test_top_level_content(module):
    """Verify each CONNECTOR_SPEC has name, description, kwargs."""
    for token in ["display_name", "description", "kwargs"]:
        assert token in module.CONNECTOR_SPEC, \
            "Can't find `{}` in CONNECTOR_SPEC".format(token)


# Cartesian product of the list of modules and the desired token
@pytest.mark.parametrize('module', MODULES)
@pytest.mark.parametrize('token', ["default", "type", "help"])
@pytest.mark.parametrize('spec', ['kwargs', 'settings'])
def test_kwargs_settings_items(module, token, spec):
    """Verify config for each kwarg (or setting) has the desired token.

    (tokens given by parameters: default, type, help.)
    """
    for kwarg, config in module.CONNECTOR_SPEC[spec].items():
        assert token in config, \
            "Can't find `{}` for kwarg `{}`".format(token, kwarg)


@pytest.mark.parametrize('module', MODULES)
@pytest.mark.parametrize('spec', ['kwargs', 'settings'])
def test_kwargs_settings_type(module, spec):
    """kwarg or setting 'type' must be an actual type."""
    for kwarg, config in module.CONNECTOR_SPEC[spec].items():
        kwarg_type = config['type']
        # NOTE: we want to extend this to make it any kind
        #   of callable, that returns the object we want
        #   (it's supposed to work as a Django validator.)
        #   But this is tricky to test.  For now we'll
        #   accept any kind of "class" (i.e., a constructor.)
        assert isinstance(kwarg_type, type), \
            "'{}': not a type (in module '{}', kwarg '{}')" \
            "".format(kwarg_type, module.__name__, kwarg)


@pytest.mark.parametrize('module', MODULES)
@pytest.mark.parametrize('spec', ['kwargs', 'settings'])
def test_kwargs_settings_type_has_name(module, spec):
    """kwarg or setting 'type' must have a name."""
    for _, config in module.CONNECTOR_SPEC[spec].items():
        kwarg_type = config['type']
        assert hasattr(kwarg_type, '__name__')


@pytest.mark.parametrize('module', MODULES)
@pytest.mark.parametrize('spec', ['kwargs', 'settings'])
def test_kwargs_settings(module, spec):
    """'kwargs'  and 'settings' must be OrderedDicts."""
    assert isinstance(module.CONNECTOR_SPEC[spec], OrderedDict)
