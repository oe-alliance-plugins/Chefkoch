from setuptools import setup
import setup_translate

pkg = 'Extensions.Chefkoch'
setup(name='enigma2-plugin-extensions-chefkoch',
       version='3.0',
       description='Chefkoch Plugin',
       package_dir={pkg: 'Chefkoch'},
       packages=[pkg],
       package_data={pkg: ['images/*.png', '*.png', '*.xml', 'locale/*/LC_MESSAGES/*.mo', 'db/VKATdb', 'pic/FHD/*.png', 'pic/HD/*.png']},
       cmdclass=setup_translate.cmdclass,  # for translation
      )
