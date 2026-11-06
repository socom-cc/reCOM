/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body unparsed:src/posix/strcasecmp.cpp:37 */
/* held from src/posix/strcasecmp.cpp:37 */
/* port: provider - strcasecmp is newlib (artifacts.library=newlib); never defined in src/ */
#if 0
int
__strcasecmp (const char *s1, const char *s2 LOCALE_PARAM)
{
#if defined _LIBC && !defined USE_IN_EXTENDED_LOCALE_MODEL
	locale_t loc = _NL_CURRENT_LOCALE;
#endif
	const unsigned char *p1 = (const unsigned char *) s1;
	const unsigned char *p2 = (const unsigned char *) s2;
	int result;
	if (p1 == p2)
		return 0;
	while ((result = TOLOWER (*p1) - TOLOWER (*p2++)) == 0)
		if (*p1++ == '\0')
			break;
	return result;
}
#endif
