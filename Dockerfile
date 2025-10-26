FROM php:8.2-apache

# Install required extensions
RUN docker-php-ext-install mysqli pdo pdo_mysql

# Enable Apache mod_rewrite
RUN a2enmod rewrite

# Copy application files
COPY . /var/www/html/

# Set proper permissions
RUN chown -R www-data:www-data /var/www/html/
RUN chmod 755 /var/www/html/
RUN chmod 666 /var/www/html/users.json

# Create error log file
RUN touch /var/www/html/error.log
RUN chmod 666 /var/www/html/error.log

# Expose port
EXPOSE 80

CMD ["apache2-foreground"]