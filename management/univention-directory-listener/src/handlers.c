/*
 * Univention Directory Listener
 *  handler.c
 *
 * Like what you see? Join us!
 * https://www.univention.com/about-us/careers/vacancies/
 *
 * Copyright 2004-2025 Univention GmbH
 *
 * https://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <https://www.gnu.org/licenses/>.
 */

/*
 * The Python handlers (and possibly, C and Shell handlers in the future)
 * are initialized and run here.
 */

#include <dirent.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <limits.h>
#include <sys/types.h>
#define PY_SSIZE_T_CLEAN
#include <python3.11/Python.h>
#include <python3.11/compile.h>
#include <python3.11/marshal.h>
#include <univention/debug.h>

#include "cache_lowlevel.h"
#include "base64.h"
#include "common.h"
#include "filter.h"
#include "handlers.h"

#if PY_MAJOR_VERSION >= 3
#define PyString_FromString PyUnicode_FromString
#define PyString_FromStringAndSize PyBytes_FromStringAndSize
#define PyString_AsString PyUnicode_AsUTF8
#endif

static PyObject *handlers_argtuple(const char *dn, CacheEntry *new, CacheEntry *old);
static PyObject *handlers_argtuple_command(const char *dn, CacheEntry *new, CacheEntry *old, char *command);

extern char **module_dirs;
extern int module_dir_count;

/* Linked list of handlers. */
Handler *handlers = NULL;


/* Import a Python module (source or compiled) the same way __import__ does.
   Unfortunately there doesn't seem to be any higher level interface for this.
   I agree this isn't very intuitive. */
static PyObject *module_import(char *filename) {
	/* It is essential that every module is imported under a different name;
	   This used to be strdup("") which caused the modules to get overwritten,
	   and as a consequence thereof, the handlers were called with a different
	   module providing the global variables, which messed up big time;
	   This is due to the fact that Python remembers which modules have already
	   been imported even in these low-level functions */
	char *name = strdup(filename);
	char *namep;
	char *source_buf;
	FILE *fp;
	long size;
	size_t sizeread;
	PyObject *co;
	PyObject *m;

	if ((fp = fopen(filename, "rb")) == NULL)
		return NULL;
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "Load file %s", filename);

	namep = strrchr(filename, '.');
	if ((namep != NULL) && (strcmp(namep, ".pyo") == 0)) {
		__attribute__((unused)) long magic;

		magic = PyMarshal_ReadLongFromFile(fp);
		/* we should probably check the magic here */
		(void)PyMarshal_ReadLongFromFile(fp);

		co = PyMarshal_ReadLastObjectFromFile(fp);
	} else {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "Read and compile %s", filename);
		fseek(fp, 0, SEEK_END);
		size = ftell(fp);
		fseek(fp, 0, SEEK_SET);
		source_buf = malloc(size + 1);
		sizeread = fread(source_buf, size, 1, fp);
		source_buf[size] = '\0';
		if (sizeread == (size_t) size) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "Reading %s failed: %ld != %ld", filename, sizeread, size);
			co = NULL;
		}
		else {
			co = Py_CompileString(source_buf, filename, Py_file_input);
		}
		free(source_buf);
	}
	fclose(fp);

	if (co == NULL || !PyCode_Check(co)) {
		Py_XDECREF(co);
		free(name);
		return NULL;
	}

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "execCodeModuleEx %s", filename);
	m = PyImport_ExecCodeModuleEx(name, co, filename);
	free(name);
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "Module done %s", filename);

	return m;
}


/* Retrieve object from Python module.  */
static PyObject *module_get_object(PyObject *module, char *name) {
	if (!PyObject_HasAttrString(module, name))
		return NULL;
	return PyObject_GetAttrString(module, name);
}


/* Retrieve bool(name) from Python module.  */
static bool module_get_bool(PyObject *module, char *name) {
	PyObject *attr;
	int result;
	attr = module_get_object(module, name);
	result = PyObject_IsTrue(attr);
	Py_XDECREF(attr);
	return result == 1;
}


/* Retrieve string from Python module. */
static char *module_get_string(PyObject *module, char *name) {
	PyObject *var;
	char *str1, *str2 = NULL;

	if ((var = PyObject_GetAttrString(module, name)) == NULL)
		goto error1;
	if (!PyUnicode_Check(var))
	    goto error0;
	if (PyArg_Parse(var, "s", &str1) != 1)
	    goto error0;
	str2 = strdup(str1);
error0:
	Py_XDECREF(var);
error1:
	return str2;
}


/* Retrieve list of strings from Python module. */
static char **module_get_string_list(PyObject *module, char *name) {
	PyObject *list;
	char **res = NULL;
	int len, i;

	if ((list = PyObject_GetAttrString(module, name)) == NULL)
		goto error0;
	if (!PyList_Check(list))
		goto error1;

	len = PyList_Size(list);
	if ((res = malloc((len + 1) * sizeof(char *))) == NULL)
		goto error1;
	for (i = 0; i < len; i++) {
		PyObject *var;
		var = PyList_GetItem(list, i);
		res[i] = strdup(PyString_AsString(var));
		Py_XDECREF(var);
	}
	res[len] = NULL;
error1:
	Py_XDECREF(list);
	if (PyErr_Occurred())
		PyErr_Print();
error0:
	PyErr_Clear();  // Silent error when attribute is not set
	return res;
}


/* Insert handler in sorted order */
static void insert_handler(Handler *handler) {
	Handler **ptr = &handlers;

	while (*ptr && (*ptr)->priority <= handler->priority)
		ptr = &((*ptr)->next);

	handler->next = *ptr;
	*ptr = handler;
}


/* load handler and insert it into list of handlers */
static int handler_import(char *filename) {
	char *filter, *error_msg = NULL;
	int num_filters = 0;
	char state_filename[PATH_MAX];
	FILE *state_fp;
	Handler *handler;
	int rv;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "importing handler %s", filename);

	if ((handler = malloc(sizeof(Handler))) == NULL)
		return 1;
	memset(handler, 0, sizeof(Handler));

	if ((handler->module = module_import(filename)) == NULL) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "import of filename=%s failed", filename);
		error_msg = "module_import()";
		goto error;
	}

	handler->name = module_get_string(handler->module, "name"); /* optional */
	if (handler->name == NULL || !handler->name) {
		free(handler->name);
		char *dot = rindex(filename, '.');
		char *slash = rindex(filename, '/');
		char *basename = slash ? slash + 1 : filename;
		handler->name = strndup(basename, dot - slash - 1);
	}

	if (PyObject_HasAttrString(handler->module, "modrdn")) { /* optional */
		handler->modrdn = module_get_bool(handler->module, "modrdn");
	}
	PyErr_Clear();  // Silent error when attribute is not set

	do { /* optional */
		handler->priority = PRIORITY_DEFAULT;
		PyObject *var = PyObject_GetAttrString(handler->module, "priority");
		if (!var)
			break;
		handler->priority = PyFloat_AsDouble(var);
		Py_XDECREF(var);
	} while(0);
	PyErr_Clear(); // Silent error when attribute is not set

	do { /* optional */
		PyObject *var = PyObject_GetAttrString(handler->module, "handle_every_delete");
		if (!var)
			break;
		handler->handle_every_delete = PyObject_IsTrue(var);
		Py_XDECREF(var);
	} while(0);
	PyErr_Clear(); // Silent error when attribute is not set

	handler->description = module_get_string(handler->module, "description"); /* required */
	if (handler->description == NULL) {
		error_msg = "module_get_string(\"description\")";
		goto error;
	}

	if ((filter = module_get_string(handler->module, "filter")) != NULL) { /* optional */
		handler->filters = realloc(handler->filters, (num_filters + 2) * sizeof(struct filter *));
		if (handler->filters == NULL) {
			error_msg = "malloc(struct filter[])";
			goto error;
		}
		handler->filters[0] = malloc(sizeof(struct filter));
		if (handler->filters[0] == NULL) {
			error_msg = "malloc(struct filter)";
			goto error;
		}
		handler->filters[0]->base = NULL;
		handler->filters[0]->scope = LDAP_SCOPE_SUBTREE;
		handler->filters[0]->filter = filter;
		num_filters++;
		handler->filters[num_filters] = NULL;
	} else {
		PyErr_Clear();  // Silent error when attribute is not set
	}

	handler->attributes = module_get_string_list(handler->module, "attributes"); /* optional */
	if (handler->attributes == NULL) {
		PyErr_Clear();  // Silent error when attribute is not set
	}

	handler->handler = module_get_object(handler->module, "handler");
	handler->initialize = module_get_object(handler->module, "initialize");
	handler->clean = module_get_object(handler->module, "clean");
	handler->prerun = module_get_object(handler->module, "prerun");
	handler->postrun = module_get_object(handler->module, "postrun");
	handler->setdata = module_get_object(handler->module, "setdata");

	/* read handler state */
	rv = snprintf(state_filename, PATH_MAX, "%s/handlers/%s", cache_dir, handler->name);
	if (rv < 0 || rv >= PATH_MAX)
		abort();
	state_fp = fopen(state_filename, "r");
	if (state_fp == NULL) {
		handler->state = 0;
	} else {
		rv = fscanf(state_fp, "%u", &handler->state);
		if (rv != 1)
			univention_debug(UV_DEBUG_LDAP, UV_DEBUG_WARN, "Failed reading %s: %s", state_filename, strerror(errno));
		fclose(state_fp);
	}

	insert_handler(handler);

	return 0;
error:
	if (PyErr_Occurred()) {
		PyErr_Print();
	}
	Py_XDECREF(handler->setdata);
	Py_XDECREF(handler->postrun);
	Py_XDECREF(handler->prerun);
	Py_XDECREF(handler->clean);
	Py_XDECREF(handler->initialize);
	Py_XDECREF(handler->handler);
	if (handler->attributes) {
		char **c;
		for (c = handler->attributes; *c; c++)
			free(*c);
		free(handler->attributes);
	}
	while (num_filters-- > 0) {
		free(handler->filters[num_filters]->filter);
		free(handler->filters[num_filters]->base);
		free(handler->filters[num_filters]);
	}
	free(handler->filters);
	free(handler->description);
	free(handler->name);
	free(handler);
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "import of filename=%s failed in %s", filename, error_msg ? error_msg : "???");
	return 1;
}


/* run prerun handler; this only needs to be done once for multiple calls
   to the same handler until the postrun handler is run */
static int handler_prerun(Handler *handler) {
	if (handler->prerun && !handler->prepared) {
		PyObject *result = PyObject_CallObject(handler->prerun, NULL);
		drop_privileges();
		if (result == NULL) {
			PyErr_Print();
			return 1;
		}
		Py_XDECREF(result);
	}
	handler->prepared = 1;

	return 0;
}


/* run postrun handler */
static int handler_postrun(Handler *handler) {
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "postrun handler: %s (prepared=%d)", handler->name, handler->prepared);
	if (!handler->prepared)
		return 0;
	if (handler->postrun) {
		PyObject *result = PyObject_CallObject(handler->postrun, NULL);
		drop_privileges();
		if (result == NULL) {
			PyErr_Print();
			return 1;
		}
		Py_XDECREF(result);
	}
	handler->prepared = 0;

	return 0;
}


/* run all postrun handlers. */
int handlers_postrun_all(void) {
	Handler *cur;

	for (cur = handlers; cur != NULL; cur = cur->next) {
		handler_postrun(cur);
	}
	return 0;
}


/* execute handler with arguments */
static int handler_exec(Handler *handler, const char *dn, CacheEntry *new, CacheEntry *old, char command) {
	PyObject *argtuple, *result;
	int rv = 0;
	char cmd[2];

	if ((handler->state & HANDLER_READY) != HANDLER_READY) {
		if (INIT_ONLY) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "handler: %s (not ready) (ignore)", handler->name);
		} else {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "handler: %s (not ready)", handler->name);
			return 1;
		}
	}

	if (handler->modrdn) {
		cmd[0] = command;
		cmd[1] = '\0';
		argtuple = handlers_argtuple_command(dn, new, old, cmd);
	} else {
		argtuple = handlers_argtuple(dn, new, old);
	}
	handler_prerun(handler);

	result = PyObject_CallObject(handler->handler, argtuple);
	drop_privileges();
	Py_XDECREF(argtuple);
	if (result == NULL) {
		PyErr_Print();
		rv = -1;
	} else {
		rv = result == Py_None ? 0 : 1;
		Py_XDECREF(result);
	}

	return rv;
}


/* call clean function of handler */
int handler_clean(Handler *handler) {
	PyObject *result;

	if (handler->clean == NULL)
		return 0;

	result = PyObject_CallObject(handler->clean, NULL);
	drop_privileges();
	if (result == NULL) {
		PyErr_Print();
		return 1;
	}

	Py_XDECREF(result);
	return 0;
}


/* call clean function on all handlers. */
int handlers_clean_all(void) {
	Handler *cur;
	for (cur = handlers; cur != NULL; cur = cur->next) {
		handler_clean(cur);
	}
	return 0;
}


/* call handler's initialize function */
int handler_initialize(Handler *handler) {
	PyObject *result;

	if (handler->initialize == NULL)
		return 0;
	result = PyObject_CallObject(handler->initialize, NULL);
	drop_privileges();
	if (result == NULL) {
		PyErr_Print();
		return 1;
	}

	Py_XDECREF(result);
	return 0;
}


/* call initialize function on all handlers. */
int handlers_initialize_all(void) {
	Handler *cur;
	for (cur = handlers; cur != NULL; cur = cur->next) {
		handler_initialize(cur);
	}
	return 0;
}


/* Load all handlers from one directory. */
int handlers_load_path(char *path) {
	struct stat st;
	int rv = 1;

	stat(path, &st);
	if (S_ISDIR(st.st_mode)) {
		DIR *dir;
		struct dirent *de;

		dir = opendir(path);
		while ((de = readdir(dir))) {
				char *s = strrchr(de->d_name, '.');
				/* Only load *.py files */
				if ((s != NULL) && (strcmp(s, ".py") == 0)) {
					char filename[PATH_MAX];
					rv = snprintf(filename, PATH_MAX, "%s/%s", path, de->d_name);
					if (rv < 0 || rv >= PATH_MAX)
						abort();
					rv = handler_import(filename);
				}
		}
		closedir(dir);
	} else if (S_ISREG(st.st_mode)) {
		handler_import(path);
	} else {
		return 1;
	}

	return rv;
}


/* Load handlers from all directories. */
static int handlers_load_all_paths(void) {
	char **module_dir;

	for (module_dir = module_dirs; module_dir != NULL && *module_dir != NULL; module_dir++) {
		handlers_load_path(*module_dir);
	}

	return 0;
}


void handler_write_state(Handler *handler) {
	char state_filename[PATH_MAX];
	FILE *state_fp;
	int rv;

	/* write handler state */
	/* XXX: can be removed, once we use a database for this */
	rv = snprintf(state_filename, PATH_MAX, "%s/handlers/%s", cache_dir, handler->name);
	if (rv < 0 || rv >= PATH_MAX)
		abort();
	state_fp = fopen(state_filename, "w");
	if (state_fp == NULL) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "could not open %s", state_filename);
	} else {
		fprintf(state_fp, "%d", handler->state);
		rv = fclose(state_fp);
		if (rv != 0)
			abort_io("close", state_filename);
	}
}


/* Free one handler. */
int handler_free(Handler *handler) {
	char **a;
	struct filter **f;

	if (handler == NULL || handler->name == NULL) {
		return 0;
	}

	handler_write_state(handler);

	/* free list node */
	free(handler->name);
	free(handler->description);
	for (f = handler->filters; f != NULL && *f != NULL; f++) {
		free((*f)->base);
		free((*f)->filter);
		free(*f);
	}
	free(handler->filters);
	for (a = handler->attributes; a != NULL && *a != NULL; a++)
		free(*a);
	free(handler->attributes);
	Py_XDECREF(handler->module);
	Py_XDECREF(handler->handler);
	Py_XDECREF(handler->initialize);
	Py_XDECREF(handler->clean);
	Py_XDECREF(handler->prerun);
	Py_XDECREF(handler->postrun);

	return 0;
}


/* Free all handlers. */
int handlers_free_all(void) {
	Handler *cur;

	while (handlers != NULL) {
		cur = handlers;
		handlers = handlers->next;
		handler_free(cur);
		free(cur);
	}

	return 0;
}


/* Reload handlers from all paths. */
int handlers_reload_all_paths(void) {
	handlers_free_all();
	return handlers_load_all_paths();
}


/* Initialize all handlers. */
int handlers_init(void) {
	/* all byte-compiled Univention Python modules are compiled optimized,
	   so we'll better run handlers optimized as well */
	Py_OptimizeFlag++;
	Py_UnbufferedStdioFlag++;
	Py_Initialize();
	handlers_load_all_paths();
	return 0;
}


/* convert our C entry structure into a Python dictionary */
static PyObject *handlers_entrydict(CacheEntry *entry) {
	PyObject *entrydict;
	PyObject *valuelist, *s;
	int i, j;

	if ((entrydict = PyDict_New()) == NULL)
		return NULL;

	if (entry == NULL)
		return entrydict;

	for (i = 0; i < entry->attribute_count; i++) {
		/* make value list */
		if ((valuelist = PyList_New(entry->attributes[i]->value_count)) == NULL) {
			Py_XDECREF(entrydict);
			return NULL;
		}
		s = PyString_FromString(entry->attributes[i]->name);

		for (j = 0; j < entry->attributes[i]->value_count; j++) {
			PyList_SetItem(valuelist, j, PyString_FromStringAndSize(entry->attributes[i]->values[j], entry->attributes[i]->length[j] - 1));
		}

		PyDict_SetItem(entrydict, s, valuelist);
		Py_XDECREF(s);
		Py_XDECREF(valuelist);
	}

	return entrydict;
}


/* build Python argument tuple for handler */
static PyObject *handlers_argtuple(const char *dn, CacheEntry *new, CacheEntry *old) {
	PyObject *argtuple;
	PyObject *newdict;
	PyObject *olddict;

	/* make argument list */
	if ((argtuple = PyTuple_New(3)) == NULL)
		return NULL;
	newdict = handlers_entrydict(new);
	olddict = handlers_entrydict(old);

	/* PyTuple_SetItem steals a reference. Thus there's no need to
	   DECREF the objects */
	PyTuple_SetItem(argtuple, 0, PyString_FromString(dn));
	PyTuple_SetItem(argtuple, 1, newdict);
	PyTuple_SetItem(argtuple, 2, olddict);

	return argtuple;
}


/* build Python argument tuple for handler with mod_rdn enabled. */
static PyObject *handlers_argtuple_command(const char *dn, CacheEntry *new, CacheEntry *old, char *command) {
	PyObject *argtuple;
	PyObject *newdict;
	PyObject *olddict;

	/* make argument list */
	if ((argtuple = PyTuple_New(4)) == NULL)
		return NULL;
	newdict = handlers_entrydict(new);
	olddict = handlers_entrydict(old);

	/* PyTuple_SetItem steals a reference. Thus there's no need to
	   DECREF the objects */
	PyTuple_SetItem(argtuple, 0, PyString_FromString(dn));
	PyTuple_SetItem(argtuple, 1, newdict);
	PyTuple_SetItem(argtuple, 2, olddict);
	PyTuple_SetItem(argtuple, 3, PyString_FromString(command));

	return argtuple;
}


/* return boolean indicating whether attribute has changed */
static int attribute_has_changed(char **changes, char *attribute) {
	char **cur;

	for (cur = changes; cur != NULL && *cur != NULL; cur++) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "%s ? %s", *cur, attribute);
		if (strcmp(*cur, attribute) == 0)
			return 1;
	}

	return 0;
}


/* a little more low-level interface than handler_update */
static int handler__update(Handler *handler, const char *dn, CacheEntry *new, CacheEntry *old, char command, char **changes) {
	int matched;
	int rv = 0;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "handler: %s considered", handler->name);

	/* check if attributes for handler have changed

	   the replication handler should be checked for the changed object in any case,
	   especially if we have an incomplete cache
	*/
	if ((strcmp(handler->name, "replication")) && cache_entry_module_present(old, handler->name)) {
		char **cur;
		bool uptodate = false;

		if (changes == NULL) {
			uptodate = true;
			goto up_to_date;
		}
		for (cur = handler->attributes; cur != NULL && *cur != NULL; cur++) {
			if (attribute_has_changed(changes, *cur))
				break;
		}
		if (cur != NULL && *cur == NULL && handler->attributes != NULL && *handler->attributes != NULL) {
			uptodate = true;
			goto up_to_date;
		}

	up_to_date:
		if (uptodate) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (up-to-date)", handler->name);
			cache_entry_module_add(new, handler->name);
			return 0;
		}
	}

	/* check if the handler's search filter matches */
	matched = cache_entry_ldap_filter_match(handler->filters, dn, new);
	if (!matched) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "handler: %s (filter doesn't match)", handler->name);
		return 0;
	}

	/* run handler */
	if (handler_exec(handler, dn, new, old, command) == 0) {
		cache_entry_module_add(new, handler->name);
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (successful)", handler->name);
	} else {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "handler: %s (failed)", handler->name);
		rv = 1;
	}

	return rv;
}


/* run all handlers if object has changed */
int handlers_update(const char *dn, CacheEntry *new, CacheEntry *old, char command) {
	Handler *handler;
	char **changes;
	int rv = 0;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "running handlers for %s", dn);

	changes = cache_entry_changed_attributes(new, old);

	for (handler = handlers; handler != NULL; handler = handler->next) {
		if (!strcmp(handler->name, "replication")) {
			handler__update(handler, dn, new, old, command, changes);
		}
	}
	for (handler = handlers; handler != NULL; handler = handler->next) {
		if (strcmp(handler->name, "replication")) {
			handler__update(handler, dn, new, old, command, changes);
		}
	}
	free(changes);

	return rv;
}


/* run given handler if object has changed */
int handler_update(const char *dn, CacheEntry *new, CacheEntry *old, Handler *handler, char command) {
	char **changes;
	int rv = 0;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "running handlers [%s] for %s", handler->name, dn);

	changes = cache_entry_changed_attributes(new, old);

	rv = handler__update(handler, dn, new, old, command, changes);

	free(changes);

	return rv;
}


/* run handlers if object has been deleted */
int handlers_delete(const char *dn, CacheEntry *old, char command) {
	Handler *handler;
	int rv = 0;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "delete handlers for %s", dn);

	for (handler = handlers; handler != NULL; handler = handler->next) {
		/* run the replication handler in any case, see Bug #29475 */
		if (!cache_entry_module_present(old, handler->name) && strcmp(handler->name, "replication") && !handler->handle_every_delete) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (skipped)", handler->name);
			continue;
		}
		if (handler_exec(handler, dn, NULL, old, command) == 0) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (successful)", handler->name);
			cache_entry_module_remove(old, handler->name);
		} else {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (failed)", handler->name);
			rv = 1;
		}
	}

	return rv;
}


/* build filter to match objects for all modules */
char *handlers_filter(void) {
	return NULL;
}


/* Pass configuration data from listener to one module. */
static int handler_set_data(Handler *handler, PyObject *argtuple) {
	PyObject *result;
	int rv;

	if (handler == NULL)
		return 0;

	if (handler->setdata == NULL)
		return 0;

	result = PyObject_CallObject(handler->setdata, argtuple);
	drop_privileges();
	if (result == NULL) {
		PyErr_Print();
		return -1;
	}

	if (result != Py_None)
		rv = 1;
	else
		rv = 0;

	Py_XDECREF(result);
	return rv;
}


/* Pass configuration data from listener to all modules. */
int handlers_set_data_all(char *key, char *value) {
	Handler *handler;
	PyObject *argtuple;
	__attribute__((unused)) int rv = 1;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "setting data for all handlers: key=%s  value=%s", key, strcmp("bindpw", key) ? value : "<HIDDEN>");

	/* make argument list */
	if ((argtuple = PyTuple_New(2)) == NULL)
		return -1;

	PyTuple_SetItem(argtuple, 0, PyString_FromString(key));
	PyTuple_SetItem(argtuple, 1, PyString_FromString(value));

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "DEBUG: handlers=%p", handlers);
	if (handlers == NULL)
		return 0;

	for (handler = handlers; handler != NULL; handler = handler->next) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "DEBUG: handler=%p", handler);
		if (handler_set_data(handler, argtuple) < 0)
			rv = -1;
	}

	Py_XDECREF(argtuple);

	return 1;
}
